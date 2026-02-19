# QMD-Py — Query Markup Documents

[中文文档](README_CN.md)

An on-device hybrid search engine for Markdown documents. Index your notes, docs, and knowledge bases — search with keywords or natural language. Python port faithfully replicating the core algorithms of [qmd](https://github.com/tobi/qmd).

QMD-Py combines BM25 full-text search, vector semantic search, and LLM re-ranking — all running locally. Supports llama-cpp-python (GGUF models), sentence-transformers, and FlagEmbedding backends.

## Install

```bash
pip install qmd                # core
pip install "qmd[mvp]"         # + LLM backends (sentence-transformers, llama-cpp, etc.)
pip install "qmd[mcp]"         # + MCP server for Claude Desktop
pip install "qmd[mvp,mcp]"     # everything
```

## Quick Start

```bash
# Add a collection
qmd add notes ~/notes
qmd add docs ~/Documents/docs --pattern "**/*.md"

# Add context (helps LLM understand what docs are about)
qmd context add notes "" "Personal notes and ideas"
qmd context add docs "api" "API documentation"

# Generate embeddings
qmd embed

# Search
qmd search "project progress"          # BM25 keyword search
qmd query "how to deploy the service"  # Hybrid search + reranking (best quality)

# Get a document
qmd get qmd://notes/meeting.md
qmd get "#abc123"                      # by docid

# List files
qmd ls
qmd ls notes
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    QMD-Py Hybrid Search Pipeline                │
└─────────────────────────────────────────────────────────────────┘

                           ┌──────────────┐
                           │  User Query  │
                           └──────┬───────┘
                                  │
                   ┌──────────────┴──────────────┐
                   ▼                              ▼
          ┌────────────────┐            ┌─────────────────┐
          │ Query Expansion│            │  Original Query  │
          │  (fine-tuned)  │            │   (×2 weight)    │
          └───────┬────────┘            └────────┬────────┘
                  │                              │
                  │  lex / vec / hyde variants    │
                  └──────────────┬───────────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           ▼                     ▼                     ▼
     ┌───────────┐         ┌───────────┐         ┌───────────┐
     │ BM25+Vec  │         │ BM25+Vec  │         │ BM25+Vec  │
     │ (original)│         │(expanded 1)│        │(expanded 2)│
     └─────┬─────┘         └─────┬─────┘         └─────┬─────┘
           │                     │                     │
           └─────────────────────┼─────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   RRF Fusion (k=60)     │
                    │   Original ×2 weight     │
                    │   Top-rank bonus: +0.05  │
                    │   Top 40 candidates      │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │     LLM Re-ranking      │
                    │   (qwen3-reranker)      │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  Position-Aware Blend   │
                    │  Rank 1-3:  75% RRF     │
                    │  Rank 4-10: 60% RRF     │
                    │  Rank 11+:  40% RRF     │
                    └─────────────────────────┘
```

## Retrieval Algorithm

### Score Normalization

| Backend | Raw Score | Transform | Range |
|---------|-----------|-----------|-------|
| **BM25 (FTS5)** | SQLite FTS5 BM25 | `abs(score)` | 0 ~ 25+ |
| **Vector** | Cosine distance | `1 / (1 + distance)` | 0.0 ~ 1.0 |
| **Reranker** | LLM 0-10 rating | `score / 10` | 0.0 ~ 1.0 |

### Fusion Strategy

The `query` command uses **Reciprocal Rank Fusion (RRF)** with position-aware blending:

1. **Query Expansion**: Original query (×2 weight) + LLM-generated variant queries
2. **Parallel Retrieval**: Each query searches both FTS and vector indexes
3. **RRF Fusion**: `score = Σ(1/(k+rank+1))`, k=60
4. **Top-Rank Bonus**: +0.05 for #1 in any list, +0.02 for #2-3
5. **Strong Signal Detection**: Skip expansion when BM25 top-1 ≥ 0.85 and gap to top-2 ≥ 0.15
6. **Top-K Selection**: Top 40 candidates enter re-ranking
7. **LLM Re-ranking**: Score each chunk (not full document)
8. **Position-Aware Blending**:
   - RRF rank 1-3: 75% retrieval / 25% reranker (protect exact matches)
   - RRF rank 4-10: 60% retrieval / 40% reranker
   - RRF rank 11+: 40% retrieval / 60% reranker (trust reranker)

### Score Interpretation

| Score | Meaning |
|-------|---------|
| 0.8 – 1.0 | Highly relevant |
| 0.5 – 0.8 | Moderately relevant |
| 0.2 – 0.5 | Somewhat relevant |
| 0.0 – 0.2 | Low relevance |

## Smart Chunking

Documents are split into ~900-token chunks with 15% overlap, using a breakpoint detection algorithm to find natural split points:

| Pattern | Score | Description |
|---------|-------|-------------|
| `# Heading` | 100 | H1 heading |
| `## Heading` | 90 | H2 heading |
| `### Heading` | 80 | H3 heading |
| `#### ~ ######` | 70–50 | H4–H6 |
| `` ``` `` | 80 | Code fence boundary |
| `---` / `***` | 60 | Horizontal rule |
| Blank line | 20 | Paragraph boundary |
| `- item` / `1. item` | 5 | List item |
| Newline | 1 | Minimum breakpoint |

**Algorithm**: When approaching the 900-token target, search the preceding 200-token window for the best breakpoint. Score decay: `finalScore = baseScore × (1 - (distance/window)² × 0.7)`. Breakpoints inside code fences are ignored — code stays intact.

## Context System

Context is a core QMD feature — attach descriptive metadata to paths so LLMs understand what documents are about.

```bash
# Collection level
qmd context add notes "" "Personal notes and ideas"

# Sub-path level
qmd context add notes "work" "Work-related notes"
qmd context add notes "work/meetings" "Meeting notes"

# Hierarchical inheritance: searching notes/work/meetings/2024.md
# returns all matching contexts concatenated:
# → "Personal notes and ideas\nWork-related notes\nMeeting notes"

# List all contexts
qmd context list

# Remove
qmd context remove notes "work/meetings"
```

## CLI Commands

### Collection Management

```bash
qmd add <name> <path> [--pattern "**/*.md"]   # Add collection
qmd remove <name>                              # Remove collection
qmd collection rename <old> <new>              # Rename
qmd list                                       # List all collections
qmd ls [collection]                            # List files
qmd update [name]                              # Re-index
qmd status                                     # Index status
```

### Search

```bash
qmd search <query> [-c collection] [-n 10]     # BM25 search
qmd query <query> [-c collection] [-n 10]      # Hybrid search + reranking
```

### Output Formats

```bash
--format cli     # Default terminal format
--format json    # JSON (for agent consumption)
--format csv     # CSV
--format xml     # XML
--format md      # Markdown
--format files   # Simple file list: docid,score,filepath,context
--full           # Show full content
--line-numbers   # Show line numbers
```

### Document Operations

```bash
qmd get <file> [-c collection]                 # Get document
qmd get qmd://notes/file.md                    # Virtual path
qmd get "#abc123"                              # By docid
qmd get file.md:42 --max-lines 20             # Line range
qmd embed [--force]                            # Generate embeddings
qmd cleanup                                    # Clean orphaned data + VACUUM
```

## MCP Server

QMD-Py provides an MCP (Model Context Protocol) server via stdio transport for use with Claude Desktop and other MCP clients.

**Tools:**
- `qmd_search` — BM25 keyword search
- `qmd_deep_search` — Hybrid search + query expansion + reranking
- `qmd_vector_search` — Vector semantic search
- `qmd_get` — Get document (path or docid, with fuzzy match suggestions)
- `qmd_index` — Index/update collection
- `qmd_status` — Index health status
- `qmd_collections` — List collections

**Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "qmd": {
      "command": "qmd",
      "args": ["serve"]
    }
  }
}
```

## LLM Backends

QMD-Py supports three backends, auto-selected by priority:

### llama-cpp-python (recommended)

Uses GGUF models, same as the original qmd:

| Model | Purpose | Size |
|-------|---------|------|
| `embeddinggemma-300M-Q8_0` | Vector embedding | ~300MB |
| `qwen3-reranker-0.6b-q8_0` | Re-ranking | ~640MB |
| `qmd-query-expansion-1.7B-Q4_K_M` | Query expansion | ~1.1GB |

Models are downloaded from HuggingFace and cached in `~/.cache/qmd/models/`.

### sentence-transformers (fallback)

Pure Python embedding — no llama-cpp compilation needed. Good for quick testing.

### FlagEmbedding

Dedicated reranker backend (FlagReranker), can be combined with other backends.

## Data Storage

Database: `~/.config/qmd/qmd.db` (SQLite)

```sql
collections     -- Collection directory config
path_contexts   -- Path context descriptions
documents       -- Document metadata (path, title, hash, active)
documents_fts   -- FTS5 full-text index
content         -- Document content (content-addressable, SHA256 dedup)
content_vectors -- Embedding chunks (hash, seq, pos)
vectors_vec     -- sqlite-vec vector index
llm_cache       -- LLM response cache (query expansion, rerank)
```

Config file: `~/.config/qmd/qmd.yaml`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QMD_CONFIG_DIR` | `~/.config/qmd` | Config directory |
| `QMD_DATA_DIR` | `~/.cache/qmd` | Data/cache directory |
| `XDG_CONFIG_HOME` | `~/.config` | XDG config root |
| `XDG_CACHE_HOME` | `~/.cache` | XDG cache root |

## Requirements

- **Python** >= 3.11
- **SQLite** >= 3.35 (FTS5 support)
- **GPU** (optional): CUDA or Apple MPS for accelerated embedding/reranking

## Development

```bash
git clone https://github.com/iomgaa-ycz/qmd-py.git
cd qmd-py
pip install "qmd[mvp,mcp,dev]"
pytest tests/ -v
```

## Project Structure

```
qmd/
├── core/
│   ├── db.py           # SQLite database layer (schema, CRUD, FTS5, sqlite-vec)
│   ├── config.py       # YAML config management, collection/context operations
│   ├── store.py        # Document indexing (content-addressable storage, incremental updates)
│   ├── retrieval.py    # Hybrid retrieval engine (BM25 + Vector + RRF + Rerank)
│   ├── chunking.py     # Smart chunking (breakpoint detection, code fence protection)
│   ├── document.py     # Document lookup helpers (docid, fuzzy match, glob, cleanup)
│   └── watcher.py      # File watcher (watchdog, auto-index on change)
├── cli/
│   ├── main.py         # CLI entry point (argparse, all commands)
│   └── formatter.py    # Output formatting (JSON/CSV/XML/MD/Files)
├── llm/
│   ├── base.py         # LLM abstract interface
│   ├── llama_cpp.py    # llama-cpp-python backend
│   ├── sentence_tf.py  # sentence-transformers backend
│   ├── flagembed.py    # FlagEmbedding reranker backend
│   └── models.py       # Model config, GPU detection
├── mcp/
│   └── server.py       # MCP Server (stdio transport)
├── utils/
│   ├── paths.py        # Path utilities, VirtualPath (qmd://)
│   ├── snippet.py      # Snippet extraction, title extraction
│   └── hashing.py      # SHA256 content hash
└── __init__.py         # create_store() / create_llm_backend() entry points
```

## Acknowledgements

Python port of [qmd](https://github.com/tobi/qmd) by Tobias Lütke. Core retrieval algorithms, chunking strategy, and fusion logic faithfully replicate the original design.

## License

MIT

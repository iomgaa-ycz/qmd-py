---
tags:
  - note
  - SwarmEvo
creation date: 2025-12-04 11:35
modification date: 星期四 4日 十二月 2025 11:35:38
owner: project/SwarmEvo
---
# SwarmEvo 获得评分方法

## 第一步：运行程序
运行程序以在mle-bench数据集上进行评估。
```bash
# 1. 重新构建  
docker build --no-cache -t agent4med agents/agent4med/  
  
# 2. 运行  
python run_agent.py \  
--agent-id agent4med \  
--competition-set experiments/splits/low.txt \  
--n-workers 4
```

## 第二步：准备元数据
理论上运行完run_agent.py后会生成metadata.json元数据文件。但是偶尔也可能没有生成成功，这就需要自己生成。
metadata.json格式如下：
```json
{

"runs": [

"aerial-cactus-identification_dc099942-25fd-4f8b-bff3-86ac1b6b58b1",

"aptos2019-blindness-detection_068cc132-ed14-4482-ba5b-9ccc28051aad",

"denoising-dirty-documents_734f29de-0e28-4c7f-b5e2-1fe279a06770",

"detecting-insults-in-social-commentary_36397987-10d9-491f-ae5b-7d0107726db5",

"dog-breed-identification_ed95c2b8-f2dd-423d-af2a-158505a15529",

"dogs-vs-cats-redux-kernels-edition_5d3fe828-30ab-4312-b1a0-89428678e94f",

"histopathologic-cancer-detection_aa809ba8-95b2-4bd8-a9f9-8f6d0d02a4dd",

"jigsaw-toxic-comment-classification-challenge_524bac1e-84c4-4b68-8984-ea1f36a616b5",

"leaf-classification_6fb2178e-0ab3-4ecc-a285-9152fd073c0e",

"mlsp-2013-birds_9c35d6d1-a93c-4264-b1a7-5eab5fa8c9c3"

]

}
```

## 第三步：生成提交列表 (submission.jsonl) 使用 

`make_submission.py`脚本，从每个竞赛的运行目录中提取 `submission.csv`，汇总成一个列表文件。

```bash
python /home/yuchengzhang/Code/mle-bench/experiments/make_submission.py \
    --metadata /home/yuchengzhang/Code/mle-bench/runs/2026-02-16T09-38-21-GMT_run-group_swarm-evo/metadata.json \
    --output /home/yuchengzhang/Code/mle-bench/submission.jsonl
```


## 第四步：执行评分 (`mlebench grade`)
 使用 `mlebench grade`命令，它会读取 `submission.jsonl`，并调用内置的评分逻辑（对比标准答案或计算 Metric）来生成最终报告。
 ```bash
mlebench grade \
    --submission /home/yuchengzhang/Code/mle-bench/submission.jsonl \
    --output-dir /home/yuchengzhang/Code/mle-bench/grading_results
```
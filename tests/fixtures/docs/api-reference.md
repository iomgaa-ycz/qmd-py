# API Reference Documentation

This document provides a comprehensive reference for the HTTP REST API.

## Authentication

All API requests require authentication using an API key in the request header:

```http
GET /api/v1/users
Authorization: Bearer YOUR_API_KEY
```

## Base URL

```
https://api.example.com/v1
```

## Endpoints

### Users

#### Get User

Retrieves information about a specific user.

**Request:**

```http
GET /users/{userId}
```

**Parameters:**

- `userId` (required): The unique identifier of the user

**Response:**

```json
{
  "id": "12345",
  "username": "john_doe",
  "email": "john@example.com",
  "created_at": "2024-01-15T10:30:00Z",
  "status": "active"
}
```

#### Create User

Creates a new user account.

**Request:**

```http
POST /users
Content-Type: application/json

{
  "username": "new_user",
  "email": "user@example.com",
  "password": "secure_password"
}
```

**Response:**

```json
{
  "id": "67890",
  "username": "new_user",
  "email": "user@example.com",
  "created_at": "2024-02-19T14:22:00Z"
}
```

### Posts

#### List Posts

Retrieves a paginated list of posts.

**Request:**

```http
GET /posts?page=1&limit=20
```

**Parameters:**

- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 20, max: 100)

**Response:**

```json
{
  "data": [
    {
      "id": "post_123",
      "title": "Introduction to REST APIs",
      "author_id": "12345",
      "created_at": "2024-02-15T09:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 150
  }
}
```

#### Create Post

Creates a new blog post.

**Request:**

```http
POST /posts
Content-Type: application/json

{
  "title": "My New Post",
  "content": "This is the post content...",
  "tags": ["tutorial", "api"]
}
```

**Response:**

```json
{
  "id": "post_456",
  "title": "My New Post",
  "author_id": "12345",
  "created_at": "2024-02-19T14:30:00Z",
  "status": "published"
}
```

## Error Handling

The API uses standard HTTP status codes:

- `200 OK`: Request successful
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Authentication required
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

**Error Response Format:**

```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "The 'email' field is required",
    "details": {
      "field": "email"
    }
  }
}
```

## Rate Limiting

API requests are rate-limited to 100 requests per minute per API key. Rate limit information is included in response headers:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1708351200
```

## Webhooks

The API supports webhook notifications for certain events:

```python
# Example webhook payload
{
  "event": "user.created",
  "data": {
    "user_id": "12345",
    "username": "new_user"
  },
  "timestamp": "2024-02-19T14:30:00Z"
}
```

## SDK Support

Official SDKs are available for:

- Python
- JavaScript/Node.js
- Ruby
- Go

## Changelog

### Version 1.2.0 (2024-02-15)
- Added webhook support
- Improved error messages
- Performance optimizations

### Version 1.1.0 (2024-01-10)
- Added pagination to list endpoints
- New filtering options

### Version 1.0.0 (2024-01-01)
- Initial release

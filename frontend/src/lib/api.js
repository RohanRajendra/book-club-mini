/**
 * The API client.
 *
 * Every failure becomes an ApiError carrying one human sentence. The backend
 * already sends display-ready copy, so the message is shown verbatim rather
 * than replaced with our own.
 */

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const UNREACHABLE = "Can't reach the app. Is the backend running?"

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`/api${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new ApiError(UNREACHABLE, 0)
  }

  if (response.status === 204) return null

  let body = null
  try {
    body = await response.json()
  } catch {
    body = null
  }

  if (!response.ok) {
    throw new ApiError(
      body?.error || `Something went wrong (${response.status}).`,
      response.status,
    )
  }
  return body
}

const send = (method) => (path, payload) =>
  request(path, { method, body: JSON.stringify(payload) })

export const api = {
  me: () => request('/me'),
  books: () => request('/books'),
  addBook: send('POST').bind(null, '/books'),
  updateBook: (id, payload) => send('PATCH')(`/books/${id}`, payload),

  feed: (bookId, { as } = {}) =>
    request(`/books/${bookId}/feed${as ? `?as=${encodeURIComponent(as)}` : ''}`),

  createPost: (payload) => send('POST')('/posts', payload),
  editPost: (id, payload) => send('PATCH')(`/posts/${id}`, payload),
  deletePost: (id) => request(`/posts/${id}`, { method: 'DELETE' }),
  postBody: (id) => request(`/posts/${id}/body`),
}

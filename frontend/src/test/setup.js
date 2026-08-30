import { afterAll, afterEach, beforeAll } from 'vitest'
import { setupServer } from 'msw/node'

// MSW asserts on real request shapes, which is the same reasoning as respx on
// the backend. Never mock fetch directly.
export const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

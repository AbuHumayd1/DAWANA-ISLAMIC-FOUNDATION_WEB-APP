// A generation check remains necessary even if a transport ignores abort.
export function createRequestScope() {
  let current
  function invalidate() { current?.controller.abort(); current = undefined }
  return {
    invalidate,
    begin() {
      invalidate()
      const controller = new AbortController()
      current = { controller, signal: controller.signal }
      return current
    },
    current(ticket) { return current === ticket && !ticket.signal.aborted },
    assert(ticket) {
      if (current !== ticket || ticket.signal.aborted) throw new DOMException('Request cancelled.', 'AbortError')
    },
  }
}

export function createLatestResource(loader, publish) {
  const scope = createRequestScope()
  return {
    cancel(notify = false) {
      scope.invalidate()
      if (notify) publish({ data: null, loading: false, error: '', cancelled: true })
    },
    async run(parameters) {
      const ticket = scope.begin()
      publish({ data: null, loading: true, error: '' })
      try {
        const data = await loader(parameters, ticket.signal)
        if (scope.current(ticket)) publish({ data, loading: false, error: '' })
      } catch (error) {
        if (scope.current(ticket)) publish({ data: null, loading: false, error: error.name === 'AbortError' ? '' : error.message })
      }
    },
  }
}

export function assertParticipantAccess(scope, ticket, expiresAt, onExpired) {
  scope.assert(ticket)
  if (expiresAt !== null && Date.now() >= expiresAt) {
    scope.invalidate()
    onExpired()
    scope.assert(ticket)
  }
}

import { act, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ApiError } from '../src/api/client'
import { ResourceProbe, type ResourceSnapshot, type ResourceProps } from './ResourceProbe'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

type Payload = { value: string }
let resource: ResourceSnapshot
const capture = (snapshot: ResourceSnapshot) => { resource = snapshot }

function deferred() {
  let resolve!: (value: Payload) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<Payload>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

const fixture = document.querySelector<HTMLDivElement>('#fixture')!
const results = document.querySelector<HTMLPreElement>('#results')!
const root = createRoot(fixture)
const passed: string[] = []
function check(label: string, condition: boolean) {
  if (!condition) throw new Error(label)
  passed.push(label)
}
async function render(props: ResourceProps, strict = false) {
  await act(async () => {
    root.render(strict ? <StrictMode><ResourceProbe {...props} onSnapshot={capture} /></StrictMode> : <ResourceProbe {...props} onSnapshot={capture} />)
  })
}

async function run() {
  const first = deferred()
  let calls = 0
  const loadFirst = () => { calls += 1; return first.promise }
  await render({ resourceKey: 'first', load: loadFirst })
  check('An uncached page initially shows loading', fixture.textContent === 'Loading')
  await act(async () => { first.resolve({ value: 'First result' }) })
  check('A completed request displays its data', fixture.textContent === 'First result')
  await render({ resourceKey: 'first', load: loadFirst })
  check('A rerender does not fetch again', calls === 1)

  const cached = deferred()
  await render({ resourceKey: 'cached', load: () => cached.promise, cached: { value: 'Cached result' } })
  check('Cached data is visible during background loading', fixture.textContent === 'Cached result')
  await act(async () => { cached.resolve({ value: 'Updated result' }) })
  check('Background results replace the cached value', fixture.textContent === 'Updated result')

  const old = deferred()
  await render({ resourceKey: 'old', load: () => old.promise })
  const oldActions = resource
  const next = deferred()
  await render({ resourceKey: 'next', load: () => next.promise })
  check('Changing the route clears the previous page', fixture.textContent === 'Loading')
  await act(async () => { old.resolve({ value: 'Stale result' }) })
  check('An earlier route response cannot replace the new page', fixture.textContent === 'Loading')
  await act(async () => {
    oldActions.setData({ value: 'Stale mutation' })
    oldActions.setError('Stale error')
    await oldActions.reload()
  })
  await act(async () => { next.resolve({ value: 'Next result' }) })
  check('Actions from the old route cannot cancel the current request', fixture.textContent === 'Next result')

  const failed = deferred()
  await render({ resourceKey: 'failed', load: () => failed.promise })
  await act(async () => { failed.reject(new Error('Network unavailable')) })
  check('Network failures stop loading and show the fallback', fixture.textContent === 'Request failed')

  const missing = deferred()
  await render({ resourceKey: 'missing', load: () => missing.promise })
  await act(async () => { missing.reject(new ApiError('Raw server message', 404)) })
  check('Missing items use the page-specific message', fixture.textContent === 'Item not found')

  const forbidden = deferred()
  await render({ resourceKey: 'forbidden', load: () => forbidden.promise })
  await act(async () => { forbidden.reject(new ApiError('Access denied', 403)) })
  check('Other API failures retain the server message', fixture.textContent === 'Access denied')

  const requests: ReturnType<typeof deferred>[] = []
  const loadReloadable = () => {
    const request = deferred()
    requests.push(request)
    return request.promise
  }
  await render({ resourceKey: 'reloadable', load: loadReloadable })
  await act(async () => { requests[0].resolve({ value: 'Initial value' }) })
  await act(async () => { void resource.reload() })
  check('Reload keeps the current data visible', fixture.textContent === 'Initial value')
  await act(async () => { void resource.reload() })
  await act(async () => { requests[2].resolve({ value: 'Newest value' }) })
  await act(async () => { requests[1].reject(new Error('Outdated failure')) })
  check('The newest reload wins, including over old errors', fixture.textContent === 'Newest value')
  await act(async () => { void resource.reload() })
  await act(async () => { requests[3].reject(new Error('Failed reload')) })
  check('A failed reload preserves the current data', resource.data?.value === 'Newest value')
  await act(async () => { void resource.reload() })
  check('Retry clears the previous error', fixture.textContent === 'Newest value')
  await act(async () => { requests[4].resolve({ value: 'Recovered value' }) })
  check('Retry can recover from a failure', fixture.textContent === 'Recovered value')

  await act(async () => { void resource.reload() })
  await act(async () => { resource.setData((current) => ({ value: `${current?.value} + edit` })) })
  await act(async () => { requests[5].resolve({ value: 'Outdated read' }) })
  check('A successful edit cannot be overwritten by an older read', fixture.textContent === 'Recovered value + edit')

  const staleError = deferred()
  await render({ resourceKey: 'stale-error', load: () => staleError.promise })
  await render({ resourceKey: 'cached-route', load: () => Promise.resolve({ value: 'Cached route' }), cached: { value: 'Cached route' } })
  await act(async () => { staleError.reject(new Error('Old route failure')) })
  check('A previous route error cannot leak into a cached route', fixture.textContent === 'Cached route')

  const strictRequests: ReturnType<typeof deferred>[] = []
  await render({ resourceKey: 'strict', load: () => {
    const request = deferred()
    strictRequests.push(request)
    return request.promise
  } }, true)
  check('Strict Mode exercises effect cleanup and restart', strictRequests.length === 2)
  await act(async () => { strictRequests[1].resolve({ value: 'Strict result' }) })
  await act(async () => { strictRequests[0].resolve({ value: 'Abandoned effect' }) })
  check('Strict Mode ignores the abandoned effect', fixture.textContent === 'Strict result')

  const unmounted = deferred()
  await render({ resourceKey: 'unmount', load: () => unmounted.promise })
  await act(async () => { root.unmount() })
  await act(async () => { unmounted.resolve({ value: 'Unmounted result' }) })
  check('Completing a request after unmount leaves the page empty', fixture.textContent === '')
}

run().then(() => {
  results.textContent = `${passed.length} checks passed\n${passed.map((label) => `PASS: ${label}`).join('\n')}`
  document.title = 'PASS: API resource regression tests'
}).catch((error) => {
  results.textContent = `${passed.length} checks passed\nFAIL: ${error.stack ?? error}`
  document.title = 'FAIL: API resource regression tests'
})

import { useEffect } from 'react'
import { useApiResource } from '../src/hooks/useApiResource'

type Payload = { value: string }
export type ResourceSnapshot = ReturnType<typeof useApiResource<Payload>>
export type ResourceProps = {
  resourceKey: string
  load: () => Promise<Payload>
  cached?: Payload | null
}

export function ResourceProbe({
  resourceKey, load, cached = null, onSnapshot,
}: ResourceProps & { onSnapshot: (snapshot: ResourceSnapshot) => void }) {
  const snapshot = useApiResource(resourceKey, load, cached, 'Request failed', 'Item not found')
  useEffect(() => { onSnapshot(snapshot) }, [onSnapshot, snapshot])
  return <output>{snapshot.loading ? 'Loading' : snapshot.error || snapshot.data?.value || 'Empty'}</output>
}

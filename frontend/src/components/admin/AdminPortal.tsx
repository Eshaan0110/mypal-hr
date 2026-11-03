import { useCallback, useEffect, useState } from 'react'

import { api, ApiError } from '../../api/client'
import type { PolicySummary, ReferenceData, VersionAction, VersionDetail } from '../../api/types'
import { PolicyList } from './PolicyList'
import { UploadForm } from './UploadForm'
import { VersionDetailView } from './VersionDetailView'

interface Props {
  devUser: string
}

function message(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

/** HR administration: the policy register, upload, review and publication. */
export function AdminPortal({ devUser }: Props) {
  const [policies, setPolicies] = useState<PolicySummary[] | null>(null)
  const [reference, setReference] = useState<ReferenceData | null>(null)
  const [selected, setSelected] = useState<VersionDetail | null>(null)
  const [uploading, setUploading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(() => {
    api
      .adminPolicies(devUser)
      .then((list) => {
        setPolicies(list)
        setLoadError(null)
      })
      .catch((error) => setLoadError(message(error, 'The policy register could not be loaded.')))
  }, [devUser])

  useEffect(() => {
    refresh()
    api.adminReference(devUser).then(setReference).catch(() => setReference(null))
  }, [devUser, refresh])

  async function open(versionId: string) {
    setUploading(false)
    setActionError(null)
    try {
      setSelected(await api.adminVersion(versionId, devUser))
    } catch (error) {
      setActionError(message(error, 'The version could not be loaded.'))
    }
  }

  async function act(action: VersionAction, reason?: string) {
    if (!selected) return
    setBusy(true)
    setActionError(null)
    try {
      setSelected(await api.adminAction(selected.id, action, devUser, reason))
      refresh()
    } catch (error) {
      setActionError(message(error, 'The action failed. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  const policy = selected ? policies?.find((p) => p.policy_key === selected.policy_key) : undefined
  const active = policy?.versions.find((v) => v.status === 'active' && v.id !== selected?.id)

  return (
    <div className="mx-auto grid max-w-6xl gap-6 px-4 py-6 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <section aria-labelledby="register-heading">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 id="register-heading" className="text-base font-semibold">
            Policy register
          </h2>
          <button
            type="button"
            onClick={() => {
              setSelected(null)
              setUploading(true)
            }}
            disabled={!reference || !policies}
            className="rounded-md bg-brand-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            Upload
          </button>
        </div>
        {loadError && (
          <p role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
            {loadError}
          </p>
        )}
        {policies === null && !loadError ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (
          policies && <PolicyList policies={policies} selectedVersionId={selected?.id ?? null} onSelect={open} />
        )}
      </section>

      <section aria-label="Details">
        {uploading && reference && policies ? (
          <UploadForm
            policies={policies}
            reference={reference}
            devUser={devUser}
            onCancel={() => setUploading(false)}
            onUploaded={(version) => {
              setUploading(false)
              setSelected(version)
              refresh()
            }}
          />
        ) : selected ? (
          <VersionDetailView
            version={selected}
            devUser={devUser}
            activeLabel={active?.version_label ?? null}
            busy={busy}
            error={actionError}
            onAction={act}
          />
        ) : (
          <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-8 text-sm text-slate-600">
            {actionError ?? 'Choose a version to review it, or upload a new one.'}
          </div>
        )}
      </section>
    </div>
  )
}

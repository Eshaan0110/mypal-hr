import type { Citation } from '../api/types'
import { citationDetails } from '../format'

/** Where the answer comes from. Every field is built by the server from the database. */
export function Citations({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null
  return (
    <section aria-label="Sources" className="mt-4 border-t border-slate-100 pt-3">
      <h3 className="text-xs font-medium tracking-wide text-slate-500 uppercase">
        {citations.length === 1 ? 'Source' : 'Sources'}
      </h3>
      <ol className="mt-2 space-y-2">
        {citations.map((citation) => (
          <li key={citation.chunk_id} className="text-sm">
            <div className="font-medium text-slate-800">
              {citation.source_link ? (
                <a
                  href={citation.source_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-brand-700 underline decoration-brand-100 underline-offset-2 hover:decoration-brand-600"
                >
                  {citation.policy_title}
                </a>
              ) : (
                citation.policy_title
              )}{' '}
              <span className="font-normal text-slate-500">{citation.version_label}</span>
            </div>
            <div className="text-xs text-slate-600">{citationDetails(citation)}</div>
            {citation.heading_path.length > 0 && (
              <div className="text-xs text-slate-500">{citation.heading_path.join(' › ')}</div>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}

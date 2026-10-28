import { useEffect, useState } from 'react'
import { participantRequest } from '../../services/participantApi'
import { camperScoringPath } from '../../services/activityScoring'

export function CamperScorePanels({ data, onPage, onRefresh }) {
  return <div className="camper-scoring">
    <div className="portal-id-actions"><h2>Camp points</h2><button type="button" onClick={onRefresh}>Refresh points</button></div>
    {!data.ready && <p className="participant-notice" role="status">{data.message}</p>}
    {data.ready && <>
      <section className="participant-summary"><h3>My verified points</h3><p className="camper-point-total">{data.total}</p><p>Individual awards, including reversals. Each award credits the house assigned when it was recorded.</p></section>
      <section className="camper-score-section"><h3>My scoring history</h3>
        <ul className="camper-score-history">{data.history.map(row => <li key={row.id}><div><strong>{row.activity}</strong><p>{row.date}{row.slot ? ` · ${row.slot.replaceAll('_', ' ')}` : ''} · {row.house}</p></div><span>{row.reversed ? <><s>+{row.points}</s> · Reversed (0)</> : `+${row.points}`}</span></li>)}</ul>
        {!data.history.length && <p>No verified individual awards recorded.</p>}
        {data.count > data.page_size && <div className="portal-id-actions"><button type="button" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Previous awards</button><span>Page {data.page} of {Math.ceil(data.count / data.page_size)}</span><button type="button" disabled={data.page * data.page_size >= data.count} onClick={() => onPage(data.page + 1)}>Next awards</button></div>}
      </section>
      <section className="camper-score-section"><h3>My house individual leaderboard{data.house ? ` · ${data.house}` : ''}</h3>
        <p>Current members’ individual contributions credited to this house. Your personal total may include earlier contributions to another house.</p>
        {data.house ? <ol className="camper-score-list" aria-label="My house individual leaderboard">{data.house_leaderboard.map((row, index) => <li key={index} className={row.own ? 'is-own-score' : ''}><span>{row.rank}</span><span>{row.name}{row.own ? ' (You)' : ''}</span><strong>{row.points}</strong></li>)}</ol> : <p>A valid current house assignment is required to view a house individual leaderboard.</p>}
      </section>
    </>}
    <section className="camper-score-section"><h3>Overall house standings</h3>
      {data.standings_ready ? <><ol className="camper-score-list" aria-label="Overall house standings">{data.standings.map(row => <li key={row.house_id}><span>{row.rank}</span><span>{row.name}</span><strong>{row.net}</strong></li>)}</ol>{!data.standings.length && <p>No participant houses configured.</p>}</> : <p>House standings are awaiting database setup.</p>}
    </section>
  </div>
}

export default function CamperScores({ item, children, destination }) {
  const [state, setState] = useState(null), [pagination, setPagination] = useState({ destination, page: 1 }), [refresh, setRefresh] = useState(0)
  if (pagination.destination !== destination) setPagination({ destination, page: 1 })
  const page = pagination.destination === destination ? pagination.page : 1
  const setPage = next => setPagination({ destination, page: next })
  const path = camperScoringPath(item, page)
  useEffect(() => {
    const controller = new AbortController()
    participantRequest(path, undefined, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ path, refresh, data })
    }).catch(error => {
      if (!controller.signal.aborted) setState({ path, refresh, error: error.message })
    })
    return () => controller.abort()
  }, [path, refresh])
  if (children) return children({ data: state?.path === path && state?.refresh === refresh ? state.data : null, error: state?.path === path && state?.refresh === refresh ? state.error : '', onPage: setPage, onRefresh: () => setRefresh(value => value + 1) })
  if (state?.path !== path || state?.refresh !== refresh) return <section className="camper-score-section" aria-busy="true"><h2>Camp points</h2><p role="status">Loading your verified points…</p></section>
  if (state.error) return <section className="camper-score-section"><h2>Camp points</h2><p className="participant-error" role="alert">{state.error}</p><button type="button" className="button" onClick={() => setRefresh(value => value + 1)}>Retry points</button></section>
  return <CamperScorePanels data={state.data} onPage={setPage} onRefresh={() => setRefresh(value => value + 1)} />
}

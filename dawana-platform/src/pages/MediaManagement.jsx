export default function MediaManagement(){
 const base=(import.meta.env.VITE_API_BASE_URL||'/api/v1').replace(/\/api\/v1\/?$/,'')
 return <section className="ops-panel"><h1>Camp media management</h1><p>Upload drafts, review metadata and publish approved content in the camp content control center.</p>
 <div className="portal-id-actions">{[['campphotograph','Photos'],['campvideo','Camp videos'],['lecturerecording','Lecture recordings']].map(([model,label])=><a className="ops-button" key={model} href={`${base}/admin/dic/${model}/`}>{label}</a>)}</div><p>Publication requires a separate media publisher permission. Storage activation is controlled by the owner.</p></section>
}

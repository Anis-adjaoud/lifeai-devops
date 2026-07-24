/* Renders a subset of Markdown inside a chat bubble */
function renderInline(text) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={i}>{p.slice(2,-2)}</strong>
    if (p.startsWith('*')  && p.endsWith('*'))  return <em key={i}>{p.slice(1,-1)}</em>
    if (p.startsWith('`')  && p.endsWith('`'))  return <code key={i}>{p.slice(1,-1)}</code>
    return p
  })
}

function processBlocks(text) {
  const lines  = text.split('\n')
  const output = []
  let ulBuf = [], olBuf = []

  const flushUl = () => {
    if (ulBuf.length) { output.push(<ul key={`ul${output.length}`}>{ulBuf}</ul>); ulBuf = [] }
  }
  const flushOl = () => {
    if (olBuf.length) { output.push(<ol key={`ol${output.length}`}>{olBuf}</ol>); olBuf = [] }
  }

  lines.forEach((raw, i) => {
    const line = raw.trimEnd()

    if (!line) {
      flushUl(); flushOl()
      output.push(<br key={i} />)
      return
    }
    if (line.match(/^#{3}\s/))  { flushUl();flushOl(); output.push(<h3 key={i}>{line.slice(4)}</h3>); return }
    if (line.match(/^#{2}\s/))  { flushUl();flushOl(); output.push(<h2 key={i}>{line.slice(3)}</h2>); return }
    if (line.match(/^#{1}\s/))  { flushUl();flushOl(); output.push(<h2 key={i} style={{fontSize:'16px'}}>{line.slice(2)}</h2>); return }
    if (line.match(/^---+$/) || line.match(/^\*\*\*+$/)) { flushUl();flushOl(); output.push(<hr key={i}/>); return }

    if (line.match(/^[-*•]\s/)) {
      flushOl()
      ulBuf.push(<li key={i}>{renderInline(line.replace(/^[-*•]\s/,''))}</li>)
      return
    }
    if (line.match(/^\d+[.)]\s/)) {
      flushUl()
      olBuf.push(<li key={i}>{renderInline(line.replace(/^\d+[.)]\s/,''))}</li>)
      return
    }

    flushUl(); flushOl()
    output.push(<p key={i}>{renderInline(line)}</p>)
  })
  flushUl(); flushOl()
  return output
}

export default function MarkdownMessage({ text }) {
  if (!text) return null

  // Split on code blocks first
  const segments = text.split(/(```[\s\S]*?```)/g)
  const content = segments.map((seg, si) => {
    if (seg.startsWith('```')) {
      const inner = seg.slice(3).replace(/```$/, '')
      const nl = inner.indexOf('\n')
      const code = nl > -1 ? inner.slice(nl + 1) : inner
      return <pre key={si}><code>{code}</code></pre>
    }
    return <span key={si}>{processBlocks(seg)}</span>
  })

  return <div className="md-body">{content}</div>
}

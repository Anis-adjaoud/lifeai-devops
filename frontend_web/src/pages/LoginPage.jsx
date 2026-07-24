import { useGoogleFitConnect } from '../hooks/useGoogleFitConnect'

export default function LoginPage({ onConnected }) {
  const { status, connect: handleConnect } = useGoogleFitConnect(onConnected)

  return (
    <div style={{
      height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexDirection: 'column', padding: '40px',
    }}>
      {/* Card */}
      <div style={{
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.09)',
        borderRadius: 24, padding: '52px 48px',
        textAlign: 'center', maxWidth: 440, width: '100%',
        boxShadow: '0 24px 80px rgba(0,0,0,0.5)',
        backdropFilter: 'blur(24px)',
        position: 'relative', overflow: 'hidden',
      }}>
        {/* Glow bg */}
        <div style={{
          position:'absolute', top:-60, left:'50%', transform:'translateX(-50%)',
          width:200, height:200,
          background:'radial-gradient(circle, rgba(124,58,237,0.15), transparent 70%)',
          borderRadius:'50%', pointerEvents:'none',
        }}/>

        {/* Logo */}
        <div style={{
          width:72, height:72,
          background:'linear-gradient(135deg,#7c3aed,#6366f1)',
          borderRadius:20, margin:'0 auto 24px',
          display:'flex', alignItems:'center', justifyContent:'center',
          fontSize:38,
          boxShadow:'0 0 32px rgba(124,58,237,0.4)',
        }}>🏥</div>

        <h1 style={{ fontSize:26, fontWeight:800, margin:'0 0 8px', letterSpacing:'-0.5px' }}>
          LifeAI
        </h1>
        <p style={{ fontSize:14, color:'#94a3b8', margin:'0 0 32px', lineHeight:1.6 }}>
          Votre coach santé IA propulsé par <strong style={{color:'#a78bfa'}}>Gemini 2.5 Flash</strong>.
          <br/>Connectez Google Fit pour commencer votre suivi.
        </p>

        {/* Features */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:36, textAlign:'left' }}>
          {[
            ['📊', 'Dashboard santé en temps réel'],
            ['🤖', 'Chat avec votre coach IA personnel'],
            ['📱', 'Alertes WhatsApp si score critique'],
          ].map(([icon, text]) => (
            <div key={text} style={{
              display:'flex', alignItems:'center', gap:12,
              padding:'10px 14px',
              background:'rgba(255,255,255,0.03)',
              border:'1px solid rgba(255,255,255,0.07)',
              borderRadius:10, fontSize:13, color:'#cbd5e1',
            }}>
              <span style={{ fontSize:18 }}>{icon}</span>
              {text}
            </div>
          ))}
        </div>

        {/* Button */}
        {status === 'success' ? (
          <div style={{
            padding:'14px 28px', borderRadius:12,
            background:'rgba(16,185,129,0.15)',
            border:'1px solid rgba(16,185,129,0.3)',
            color:'#10b981', fontSize:15, fontWeight:600,
          }}>
            ✓ Connexion réussie !
          </div>
        ) : (
          <button
            onClick={handleConnect}
            disabled={status === 'waiting'}
            style={{
              width:'100%', padding:'14px 20px',
              borderRadius:12, border:'none', cursor: status === 'waiting' ? 'not-allowed' : 'pointer',
              background: status === 'waiting'
                ? 'rgba(255,255,255,0.06)'
                : 'linear-gradient(135deg,#7c3aed,#6d28d9)',
              color:'white', fontSize:15, fontWeight:600,
              display:'flex', alignItems:'center', justifyContent:'center', gap:12,
              transition:'all 0.2s',
              boxShadow: status === 'waiting' ? 'none' : '0 4px 20px rgba(124,58,237,0.4)',
              opacity: status === 'waiting' ? 0.7 : 1,
            }}
          >
            {status === 'waiting' ? (
              <>
                <span style={{ display:'inline-block', animation:'spin 1s linear infinite' }}>⟳</span>
                En attente de l'autorisation Google…
              </>
            ) : (
              <>
                <GoogleIcon />
                Se connecter avec Google Fit
              </>
            )}
          </button>
        )}

        {status === 'waiting' && (
          <p style={{ marginTop:14, fontSize:12, color:'#64748b' }}>
            Une fenêtre Google s'est ouverte. Autorisez l'accès puis revenez ici.
          </p>
        )}

        {status === 'blocked' && (
          <p style={{ marginTop:14, fontSize:12, color:'#f87171' }}>
            Ton navigateur a bloqué la fenêtre de connexion Google — autorise les pop-ups
            pour ce site puis réessaie.
          </p>
        )}
      </div>

      <p style={{ marginTop:20, fontSize:11, color:'#334155', textAlign:'center' }}>
        LifeAI Health Intelligence Platform
      </p>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M17.64 9.2a9.96 9.96 0 0 0-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.83.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.34A9 9 0 0 0 9 18z" fill="#34A853"/>
      <path d="M3.97 10.72A5.41 5.41 0 0 1 3.69 9c0-.6.1-1.18.28-1.72V4.94H.96A9 9 0 0 0 0 9c0 1.45.35 2.82.96 4.06l3.01-2.34z" fill="#FBBC05"/>
      <path d="M9 3.58c1.32 0 2.5.45 3.44 1.35L15 2.34A9 9 0 0 0 .96 4.94l3.01 2.34C4.68 5.16 6.66 3.58 9 3.58z" fill="#EA4335"/>
    </svg>
  )
}

import { useState, type FormEvent } from 'react'
import { ArrowRight, Eye, EyeOff, Leaf, LockKeyhole, ShieldCheck, Sprout, Wifi } from 'lucide-react'
import './login.css'

interface LoginPageProps {
  onLogin: (username: string, password: string) => Promise<void>
}

/** Decorative diagram, not a live device state or sensor reading. */
function GreenhouseDrawing() {
  return (
    <div className="ghl-drawing" role="img" aria-label="Minh họa kỹ thuật nhà kính: quạt thông gió, đèn và hệ thống phun sương">
      <div className="ghl-diagram-top">
        <span>GH—01 / FIELD DIAGRAM</span>
        <span>01 — 03</span>
      </div>
      <svg className="ghl-greenhouse-svg" viewBox="0 0 720 465" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="ghl-glass" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#B8DAB4" stopOpacity=".11" />
            <stop offset="100%" stopColor="#B8DAB4" stopOpacity=".015" />
          </linearGradient>
          <pattern id="ghl-pattern" width="30" height="30" patternUnits="userSpaceOnUse">
            <path d="M30 0H0V30" fill="none" stroke="#B6D2B6" strokeOpacity=".08" strokeWidth="1" />
          </pattern>
        </defs>
        <rect x="0" y="0" width="720" height="465" fill="url(#ghl-pattern)" />
        <path d="M65 168L360 45L655 168V404H65Z" fill="url(#ghl-glass)" stroke="#B9D8B7" strokeWidth="4" strokeLinejoin="round" />
        <path d="M360 45V404M65 168H655M168 124V404M552 124V404M168 124L360 45L552 124" stroke="#B9D8B7" strokeOpacity=".56" strokeWidth="2" />
        <path d="M65 241H655M65 313H655" stroke="#B9D8B7" strokeOpacity=".16" strokeWidth="1.5" />
        <path d="M43 405H675" stroke="#E4CE9F" strokeOpacity=".45" strokeWidth="4" />
        <path d="M130 349H590" stroke="#D9B787" strokeOpacity=".48" strokeWidth="3" />
        {[153, 226, 299, 372, 445, 518, 575].map((x, i) => (
          <g key={x}>
            <path d={`M${x} 391V${315 + i % 3 * 5}`} stroke="#A4C695" strokeWidth="3" strokeLinecap="round" />
            <path d={`M${x} 366Q${x - 36} 343 ${x - 28} 312Q${x + 7} 314 ${x} 366Z`} fill="#70A77D" fillOpacity=".85" />
            <path d={`M${x} 348Q${x + 33} 328 ${x + 29} 302Q${x - 2} 307 ${x} 348Z`} fill="#A5CA91" fillOpacity=".9" />
          </g>
        ))}
        <g transform="translate(150 210)">
          <circle r="38" fill="#17372C" stroke="#E4CE9F" strokeOpacity=".88" strokeWidth="2" />
          <circle r="24" stroke="#E4CE9F" strokeOpacity=".28" fill="none" />
          <path d="M0 -5Q-23 -34 -5 -32Q10 -22 4 -5Z M5 0Q34 -23 32 -5Q22 10 5 4Z M0 5Q23 34 5 32Q-10 22 -4 5Z M-5 0Q-34 23 -32 5Q-22 -10 -5 -4Z" fill="#D3E1C8" />
          <circle r="5" fill="#DFAE61" />
        </g>
        <path d="M451 168H579M465 168L452 215H578L565 168" stroke="#E4CE9F" strokeWidth="3" fill="none" strokeLinejoin="round" />
        <path d="M470 225L462 240M490 225L490 243M510 225L517 240M534 225L542 240" stroke="#E4CE9F" strokeOpacity=".55" strokeWidth="3" strokeLinecap="round" />
        <path d="M308 236V276M337 236V276M366 236V276M395 236V276" stroke="#A7D2C3" strokeOpacity=".5" strokeWidth="2" strokeDasharray="3 10" strokeLinecap="round" />
        <path d="M297 225H405" stroke="#A7D2C3" strokeWidth="4" strokeLinecap="round" />
        <g fontSize="13" fill="#E4CE9F" fontFamily="monospace" letterSpacing="2">
          <text x="93" y="153">FAN / 01</text>
          <text x="461" y="145">GROW LIGHT</text>
          <text x="294" y="205">MIST / 02</text>
        </g>
        <path d="M101 159L127 178M518 149L518 165M354 211V223" stroke="#E4CE9F" strokeOpacity=".55" strokeDasharray="4 4" />
        <path d="M31 436H690" stroke="#B9D8B7" strokeOpacity=".3" />
        <text x="37" y="453" fontFamily="monospace" fontSize="11" fill="#B9D8B7" letterSpacing="3">ESP32 / SENSORS / ACTUATORS</text>
        <text x="659" y="453" fontFamily="monospace" fontSize="11" fill="#B9D8B7" textAnchor="end">SCHEMATIC ONLY</text>
      </svg>
      <p className="ghl-drawing-caption">Sơ đồ minh họa — không biểu thị dữ liệu cảm biến trực tiếp</p>
    </div>
  )
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    if (!username.trim() || !password) {
      setError('Vui lòng nhập tài khoản và mật khẩu.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await onLogin(username.trim(), password)
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Không thể đăng nhập. Vui lòng thử lại.'
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="ghl-shell">
      <section className="ghl-story" aria-labelledby="ghl-story-heading">
        <div className="ghl-story-inner">
          <div className="ghl-brand"><span className="ghl-brand-icon"><Leaf size={20} aria-hidden="true" /></span><span>GREENHOUSE <small>CLIMATE OS</small></span></div>
          <div className="ghl-story-copy">
            <p className="ghl-kicker"><span className="ghl-kicker-line" /> HỆ THỐNG NHÀ KÍNH THÔNG MINH</p>
            <h1 id="ghl-story-heading">Mỗi chiếc lá,<br /><em>một tín hiệu.</em></h1>
            <p className="ghl-story-desc">Một không gian điều khiển dành cho những quyết định chính xác — từ môi trường, thiết bị đến sự an toàn của cây trồng.</p>
          </div>
          <GreenhouseDrawing />
          <div className="ghl-story-footer"><span><Wifi size={15} aria-hidden="true" /> MQTT / ESP32</span><span>REST · WEBSOCKET</span><span>FIELD NOTES / 01</span></div>
        </div>
      </section>
      <section className="ghl-entry" aria-labelledby="ghl-login-heading">
        <div className="ghl-entry-top"><span className="ghl-eyebrow">GIAO DIỆN QUẢN LÝ</span><span className="ghl-entry-mark"><Sprout size={19} aria-hidden="true" /></span></div>
        <div className="ghl-form-wrap">
          <div className="ghl-section-index">01 / TRUY CẬP HỆ THỐNG</div>
          <h2 id="ghl-login-heading">Chào mừng<br />trở lại<span className="ghl-period">.</span></h2>
          <p className="ghl-form-description">Đăng nhập để xem môi trường và vận hành nhà kính theo quyền tài khoản được cấp.</p>
          <form className="ghl-form" onSubmit={(event) => { void handleSubmit(event) }} noValidate>
            <label htmlFor="ghl-username">Tên đăng nhập hoặc email</label>
            <input id="ghl-username" name="username" type="text" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Nhập tài khoản của bạn" required disabled={submitting} maxLength={254} />
            <div className="ghl-password-heading"><label htmlFor="ghl-password">Mật khẩu</label><LockKeyhole size={14} aria-hidden="true" /></div>
            <div className="ghl-password-field">
              <input id="ghl-password" name="password" type={visible ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Nhập mật khẩu" required disabled={submitting} maxLength={1024} />
              <button type="button" aria-label={visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'} aria-pressed={visible} onClick={() => setVisible((v) => !v)} disabled={submitting}>{visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}</button>
            </div>
            {error ? <p className="ghl-error" role="alert">{error}</p> : null}
            <button className="ghl-submit" type="submit" disabled={submitting}><span>{submitting ? 'Đang xác thực…' : 'Đăng nhập hệ thống'}</span><ArrowRight size={19} aria-hidden="true" /></button>
          </form>
          <div className="ghl-security"><ShieldCheck size={19} aria-hidden="true" /><p>Phiên đăng nhập được bảo vệ bởi Backend. Quyền điều khiển thiết bị được kiểm tra tại máy chủ.</p></div>
        </div>
        <footer className="ghl-entry-footer"><span>GREENHOUSE CLIMATE IOT</span><span>SECURE ACCESS · 2026</span></footer>
      </section>
    </main>
  )
}

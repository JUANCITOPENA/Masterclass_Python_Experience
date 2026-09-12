import { useState } from 'react';
import { insforge } from '../lib/insforge';
import { useNavigate, Link } from 'react-router-dom';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    const { error } = await insforge.auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      setError(error.message);
    } else {
      navigate('/');
    }
    setLoading(false);
  };

  return (
    <div className="container mt-5">
      <div className="row justify-content-center">
        <div className="col-md-6 col-lg-4">
          <div className="card shadow-sm border-0" style={{ borderRadius: '12px' }}>
            <div className="card-body p-5">
              <div className="text-center mb-4">
                <img src="https://caesacademy.com/wp-content/uploads/2021/03/logo_02.png" alt="CAES Academy" style={{ maxWidth: '200px', marginBottom: '20px' }} />
                <h3 className="fw-bold d-flex justify-content-center align-items-center gap-2" style={{ color: '#1E4C72', fontSize: '1.3rem' }}>
                  <img src="https://img.icons8.com/stickers/1200/python.jpg" alt="Python" style={{ width: '35px', height: '35px' }} />
                  <span>Masterclass Python Experience</span>
                  <img src="https://img.icons8.com/stickers/1200/python.jpg" alt="Python" style={{ width: '35px', height: '35px' }} />
                </h3>
                <p className="text-muted mt-2">Ingresa tus credenciales para acceder al diplomado.</p>
              </div>
              
              {error && <div className="alert alert-danger">{error}</div>}

              <form onSubmit={handleLogin}>
                <div className="mb-3">
                  <label className="form-label fw-bold">Correo Electrónico</label>
                  <input type="email" className="form-control" required value={email} onChange={e => setEmail(e.target.value)} />
                </div>
                <div className="mb-4">
                  <label className="form-label fw-bold">Contraseña</label>
                  <input type="password" className="form-control" required value={password} onChange={e => setPassword(e.target.value)} />
                </div>
                <button type="submit" className="btn w-100 fw-bold shadow-sm" disabled={loading} style={{ background: '#2F6D9C', color: 'white' }}>
                  {loading ? 'Validando...' : 'Entrar al Portal'}
                </button>
              </form>

              <div className="text-center mt-4">
                <p className="text-muted small">¿No tienes acceso? <Link to="/register" className="fw-bold text-decoration-none">Regístrate aquí</Link></p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import React, { useState } from 'react';
import { insforge } from '../lib/insforge';
import { Link } from 'react-router-dom';

export default function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nombre, setNombre] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    const { error } = await insforge.auth.signUp({
      email,
      password,
      name: nombre
    });

    if (error) {
      setError(error.message);
    } else {
      setSuccess(true);
    }
    setLoading(false);
  };

  if (success) {
    return (
      <div className="container mt-5 text-center">
        <div className="alert alert-success shadow-sm mx-auto" style={{ maxWidth: '500px' }}>
          <h4 className="fw-bold">¡Registro Exitoso!</h4>
          <p>Tu cuenta ha sido creada. Tienes 7 días de acceso temporal a la plataforma.</p>
          <Link to="/login" className="btn btn-success mt-3">Ir al Login</Link>
        </div>
      </div>
    );
  }

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
                <p className="text-muted mt-2">Obtén 7 días de acceso a la Masterclass.</p>
              </div>
              
              {error && <div className="alert alert-danger">{error}</div>}

              <form onSubmit={handleRegister}>
                <div className="mb-3">
                  <label className="form-label fw-bold">Nombre Completo</label>
                  <input type="text" className="form-control" required value={nombre} onChange={e => setNombre(e.target.value)} />
                </div>
                <div className="mb-3">
                  <label className="form-label fw-bold">Correo Electrónico</label>
                  <input type="email" className="form-control" required value={email} onChange={e => setEmail(e.target.value)} />
                </div>
                <div className="mb-4">
                  <label className="form-label fw-bold">Contraseña</label>
                  <input type="password" className="form-control" required minLength={6} value={password} onChange={e => setPassword(e.target.value)} />
                </div>
                <button type="submit" className="btn w-100 fw-bold shadow-sm" disabled={loading} style={{ background: '#10B981', color: 'white' }}>
                  {loading ? 'Creando cuenta...' : 'Crear mi Acceso'}
                </button>
              </form>

              <div className="text-center mt-4">
                <p className="text-muted small">¿Ya tienes cuenta? <Link to="/login" className="fw-bold text-decoration-none">Inicia sesión</Link></p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}


import { useAuth } from '../lib/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function Masterclass() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await signOut();
    navigate('/login');
  };

  return (
    <div style={{ width: '100%', height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div className="p-2 d-flex justify-content-between align-items-center" style={{ backgroundColor: '#16202B', color: 'white', borderBottom: '2px solid #F5C518' }}>
         <span className="ms-3 fw-bold">🐍 CAES Academy PRO</span>
         <div>
           <span className="me-3">Estudiante: {user?.email}</span>
           <button onClick={handleLogout} className="btn btn-sm fw-bold" style={{ backgroundColor: '#EF4444', color: 'white' }}>Cerrar Sesión</button>
         </div>
      </div>
      <iframe src="/masterclass.html" style={{ flexGrow: 1, border: 'none', width: '100%', height: '100%' }} title="Masterclass" />
    </div>
  );
}

import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../lib/AuthContext';

export const ProtectedRoute = () => {
  const { user, subscription, loading } = useAuth();

  if (loading) {
    return <div className="d-flex justify-content-center align-items-center vh-100"><div className="spinner-border text-primary"></div></div>;
  }

  if (!user) {
    return <Navigate to="/login" />;
  }

  if (subscription) {
    const now = new Date();
    const endDate = new Date(subscription.fecha_fin);
    if (now > endDate && subscription.role !== 'admin') {
      return (
        <div className="container mt-5 text-center">
          <div className="alert alert-danger">
            <h3 className="fw-bold">Acceso Expirado</h3>
            <p>Tu tiempo de acceso a la Masterclass ha finalizado ({endDate.toLocaleDateString()}). Por favor, contacta a la academia para renovar tu acceso.</p>
          </div>
        </div>
      );
    }
  }

  return <Outlet />;
};

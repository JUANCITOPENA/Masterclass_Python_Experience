import { createContext, useContext, useEffect, useState } from 'react';
import { insforge } from './insforge';

type User = any;

interface AuthContextType {
  user: User | null;
  subscription: any | null;
  loading: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({ user: null, subscription: null, loading: true, signOut: async () => {} });

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [subscription, setSubscription] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = async () => {
    const { data: { user } } = await insforge.auth.getCurrentUser();
    setUser(user ?? null);
    if (user) {
      await fetchSubscription(user.id);
    } else {
      setSubscription(null);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUser();

    const unsubscribe = insforge.auth.onAuthStateChange(() => {
      fetchUser();
    });

    return () => {
      if (typeof unsubscribe === 'function') {
        unsubscribe();
      }
    };
  }, []);

  const fetchSubscription = async (userId: string) => {
    const { data, error } = await insforge.database
      .from('user_subscriptions')
      .select('*')
      .eq('id', userId)
      .single();
    
    if (!error && data) {
      setSubscription(data);
    }
    setLoading(false);
  };

  const signOut = async () => {
    await insforge.auth.signOut();
  };

  return (
    <AuthContext.Provider value={{ user, subscription, loading, signOut }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);

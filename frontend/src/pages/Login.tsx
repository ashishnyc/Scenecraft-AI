import { useAuth } from '../context/AuthContext';
import styles from './Login.module.css';

export default function Login() {
  const { login } = useAuth();

  const handleGoogleLogin = () => {
    // Redirect to backend Google OAuth flow
    window.location.href = `${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/auth/login`;
  };

  // Dev only: exchange a manually obtained token pair
  const handleDevLogin = async () => {
    const res = await fetch(`${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/auth/me`, {
      credentials: 'include',
    });
    if (res.ok) {
      // DEV_AUTO_LOGIN is active — server already knows who we are, create dummy tokens
      login('dev-auto-login', 'dev-auto-login');
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.logo}>SC</div>
        <h1 className={styles.title}>Scenecraft AI</h1>
        <p className={styles.subtitle}>Sign in to continue</p>

        <button className={styles.googleButton} onClick={handleGoogleLogin}>
          Sign in with Google
        </button>

        {import.meta.env.DEV && (
          <button className={styles.devButton} onClick={handleDevLogin}>
            Dev auto-login
          </button>
        )}
      </div>
    </div>
  );
}

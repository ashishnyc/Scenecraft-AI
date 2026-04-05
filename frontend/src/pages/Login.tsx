import { useAuth } from '../context/AuthContext';
import styles from './Login.module.css';

export default function Login() {
  const { login } = useAuth();

  const handleGoogleLogin = () => {
    // Redirect to backend Google OAuth flow
    window.location.href = `${import.meta.env.VITE_API_URL ?? ''}/api/auth/login`;
  };

  // Dev only: backend has DEV_AUTO_LOGIN=true so it ignores the token value.
  // Just set a dummy token to mark the frontend as authenticated.
  const handleDevLogin = () => {
    login('dev-auto-login', 'dev-auto-login');
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

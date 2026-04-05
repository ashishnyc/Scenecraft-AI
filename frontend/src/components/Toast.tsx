import { useEffect } from 'react';
import styles from './Toast.module.css';

interface ToastProps {
  message: string;
  type?: 'error' | 'success';
  onDismiss: () => void;
}

export function Toast({ message, type = 'error', onDismiss }: ToastProps) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div className={`${styles.toast} ${styles[type]}`} role="alert">
      {message}
      <button className={styles.close} onClick={onDismiss} aria-label="Dismiss">×</button>
    </div>
  );
}

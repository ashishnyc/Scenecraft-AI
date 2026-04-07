import { useState } from 'react';
import Analytics from '../pages/Analytics';
import Instagram from '../pages/Instagram';
import Settings from '../pages/Settings';
import styles from './WorkspaceModal.module.css';

type Tab = 'analytics' | 'instagram' | 'settings';

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'analytics', label: 'Analytics', icon: '∿' },
  { id: 'instagram', label: 'Instagram', icon: '⬡' },
  { id: 'settings',  label: 'Settings',  icon: '⚙' },
];

interface Props {
  onClose: () => void;
}

export function WorkspaceModal({ onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('analytics');

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.tabs}>
            {TABS.map((tab) => (
              <button
                key={tab.id}
                className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                <span className={styles.tabIcon}>{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* Tab content */}
        <div className={styles.body}>
          {activeTab === 'analytics' && <Analytics />}
          {activeTab === 'instagram' && <Instagram />}
          {activeTab === 'settings'  && <Settings />}
        </div>
      </div>
    </div>
  );
}

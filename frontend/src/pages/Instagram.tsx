/**
 * Instagram management UI (SA-67).
 * Post calendar, reply review queue, engagement dashboard.
 */
import { useState, useEffect, useCallback } from 'react';
import type { InstagramPost, InstagramComment, InstagramDashboard, PostCreate } from '../api/instagram';
import {
  fetchInstagramDashboard, fetchPosts, createPost, schedulePost,
  publishPostNow, deletePost, fetchComments, generateReply, reviewReply,
} from '../api/instagram';
import { useWorkspace } from '../context/WorkspaceContext';
import { fetchCharacters } from '../api/characters';
import type { Character } from '../api/characters';
import { Toast } from '../components/Toast';
import styles from './Instagram.module.css';

type Tab = 'dashboard' | 'calendar' | 'replies';

const STATUS_COLORS: Record<string, string> = {
  draft: '#718096',
  scheduled: '#f6ad55',
  posted: '#68d391',
  failed: '#fc8181',
};

export default function Instagram() {
  const { workspaceId } = useWorkspace();
  const [tab, setTab] = useState<Tab>('dashboard');
  const [dashboard, setDashboard] = useState<InstagramDashboard | null>(null);
  const [posts, setPosts] = useState<InstagramPost[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [selectedPost, setSelectedPost] = useState<InstagramPost | null>(null);
  const [comments, setComments] = useState<InstagramComment[]>([]);
  const [pendingComments, setPendingComments] = useState<InstagramComment[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editingReply, setEditingReply] = useState<Record<string, string>>({});

  // Create form state
  const [createForm, setCreateForm] = useState<{
    post_type: PostCreate['post_type'];
    prompt_context: string;
    character_id: string;
    media_urls: string;
  }>({ post_type: 'image', prompt_context: '', character_id: '', media_urls: '' });
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      const [dash, ps, chars] = await Promise.all([
        fetchInstagramDashboard(workspaceId),
        fetchPosts(workspaceId),
        fetchCharacters(),
      ]);
      setDashboard(dash);
      setPosts(ps);
      setCharacters(chars);

      // Load pending comments across all posted posts
      const postedIds = ps.filter(p => p.status === 'posted').map(p => p.id);
      const allComments: InstagramComment[] = [];
      await Promise.all(postedIds.slice(0, 5).map(async (id) => {
        const cs = await fetchComments(id).catch(() => []);
        allComments.push(...cs);
      }));
      setPendingComments(allComments.filter(c => c.reply_status === 'pending' && c.generated_reply));
    } catch {
      setToast({ message: 'Failed to load Instagram data', type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => { load(); }, [load]);

  const loadPostComments = async (post: InstagramPost) => {
    setSelectedPost(post);
    const cs = await fetchComments(post.id).catch(() => []);
    setComments(cs);
  };

  const handleCreate = async () => {
    if (!workspaceId || !createForm.prompt_context.trim()) return;
    setCreating(true);
    try {
      const post = await createPost({
        workspace_id: workspaceId,
        post_type: createForm.post_type,
        prompt_context: createForm.prompt_context,
        character_id: createForm.character_id || undefined,
        media_urls: createForm.media_urls ? createForm.media_urls.split('\n').map(s => s.trim()).filter(Boolean) : [],
      });
      setPosts(prev => [post, ...prev]);
      setShowCreate(false);
      setCreateForm({ post_type: 'image', prompt_context: '', character_id: '', media_urls: '' });
      setToast({ message: 'Draft post created', type: 'success' });
    } catch {
      setToast({ message: 'Failed to create post', type: 'error' });
    } finally {
      setCreating(false);
    }
  };

  const handlePublish = async (postId: string) => {
    try {
      const updated = await publishPostNow(postId);
      setPosts(prev => prev.map(p => p.id === postId ? updated : p));
      setToast({ message: 'Post published', type: 'success' });
    } catch {
      setToast({ message: 'Publish failed', type: 'error' });
    }
  };

  const handleDelete = async (postId: string) => {
    await deletePost(postId);
    setPosts(prev => prev.filter(p => p.id !== postId));
    setToast({ message: 'Post deleted', type: 'success' });
  };

  const handleGenerateReply = async (commentId: string) => {
    const updated = await generateReply(commentId).catch(() => null);
    if (updated) {
      setComments(prev => prev.map(c => c.id === commentId ? updated : c));
      setPendingComments(prev => prev.map(c => c.id === commentId ? updated : c));
    }
  };

  const handleReview = async (commentId: string, action: 'approve' | 'reject') => {
    const edited = editingReply[commentId];
    const updated = await reviewReply(commentId, action, edited).catch(() => null);
    if (updated) {
      setComments(prev => prev.map(c => c.id === commentId ? updated : c));
      setPendingComments(prev => prev.filter(c => c.id !== commentId));
      setToast({ message: action === 'approve' ? 'Reply posted' : 'Reply rejected', type: 'success' });
    }
  };

  if (loading) return <main className={styles.container}><p className={styles.empty}>Loading…</p></main>;

  return (
    <main className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Instagram</h1>
        <button className={styles.primaryBtn} onClick={() => setShowCreate(true)}>+ Generate Post</button>
      </div>

      <div className={styles.tabs}>
        {(['dashboard', 'calendar', 'replies'] as Tab[]).map(t => (
          <button key={t} className={`${styles.tab} ${tab === t ? styles.activeTab : ''}`} onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
            {t === 'replies' && pendingComments.length > 0 && (
              <span className={styles.badge}>{pendingComments.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Dashboard */}
      {tab === 'dashboard' && dashboard && (
        <div className={styles.dashSection}>
          <div className={styles.statsGrid}>
            <div className={styles.statCard}>
              <span className={styles.statValue}>{dashboard.total_posts}</span>
              <span className={styles.statLabel}>Total Posts</span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statValue}>{dashboard.total_likes.toLocaleString()}</span>
              <span className={styles.statLabel}>Total Likes</span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statValue}>{dashboard.total_comments.toLocaleString()}</span>
              <span className={styles.statLabel}>Total Comments</span>
            </div>
            <div className={styles.statCard} style={{ borderColor: dashboard.pending_reply_reviews > 0 ? '#f6ad55' : undefined }}>
              <span className={styles.statValue} style={{ color: dashboard.pending_reply_reviews > 0 ? '#f6ad55' : undefined }}>
                {dashboard.pending_reply_reviews}
              </span>
              <span className={styles.statLabel}>Pending Replies</span>
            </div>
          </div>

          <div className={styles.statusBreakdown}>
            {Object.entries(dashboard.by_status).map(([s, count]) => (
              <div key={s} className={styles.statusPill}>
                <span className={styles.statusDot} style={{ background: STATUS_COLORS[s] ?? '#718096' }} />
                <span className={styles.statusName}>{s}</span>
                <span className={styles.statusCount}>{count}</span>
              </div>
            ))}
          </div>

          {dashboard.scheduled_posts.length > 0 && (
            <>
              <h2 className={styles.sectionTitle}>Upcoming Scheduled Posts</h2>
              <ul className={styles.scheduledList}>
                {dashboard.scheduled_posts.map(p => (
                  <li key={p.id} className={styles.scheduledItem}>
                    <span className={styles.scheduledType}>{p.post_type}</span>
                    <span className={styles.scheduledCaption}>{p.caption_preview}…</span>
                    <span className={styles.scheduledTime}>{new Date(p.scheduled_at).toLocaleString()}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {/* Calendar / post list */}
      {tab === 'calendar' && (
        <div className={styles.calSection}>
          {posts.length === 0 ? (
            <div className={styles.emptyState}>
              <p className={styles.emptyTitle}>No posts yet</p>
              <p className={styles.emptySubtitle}>Generate your first Instagram post to get started.</p>
            </div>
          ) : (
            <div className={styles.postGrid}>
              {posts.map(post => (
                <div key={post.id} className={styles.postCard} onClick={() => loadPostComments(post)}>
                  <div className={styles.postCardHeader}>
                    <span className={styles.postType}>{post.post_type}</span>
                    <span className={styles.postStatus} style={{ color: STATUS_COLORS[post.status] }}>
                      {post.status}
                    </span>
                  </div>
                  <p className={styles.postCaption}>{post.caption?.slice(0, 100) ?? '(no caption)'}</p>
                  {post.hashtags.length > 0 && (
                    <p className={styles.postHashtags}>{post.hashtags.slice(0, 5).join(' ')}</p>
                  )}
                  {post.scheduled_at && (
                    <p className={styles.postTime}>📅 {new Date(post.scheduled_at).toLocaleString()}</p>
                  )}
                  <div className={styles.postActions} onClick={e => e.stopPropagation()}>
                    {post.status === 'draft' && (
                      <button className={styles.actionBtn} onClick={() => handlePublish(post.id)}>Publish Now</button>
                    )}
                    <button className={styles.dangerBtn} onClick={() => handleDelete(post.id)}>Delete</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {selectedPost && (
            <div className={styles.commentDrawer}>
              <div className={styles.commentDrawerHeader}>
                <h3>Comments — {selectedPost.caption?.slice(0, 40)}…</h3>
                <button className={styles.closeBtn} onClick={() => setSelectedPost(null)}>×</button>
              </div>
              {comments.length === 0 ? (
                <p className={styles.empty}>No comments loaded.</p>
              ) : (
                <ul className={styles.commentList}>
                  {comments.map(c => (
                    <li key={c.id} className={styles.commentItem}>
                      <div className={styles.commentHeader}>
                        <strong>@{c.author_username}</strong>
                        <span className={styles.replyStatus}>{c.reply_status}</span>
                      </div>
                      <p className={styles.commentText}>{c.text}</p>
                      {c.generated_reply && (
                        <p className={styles.generatedReply}>↩ {c.generated_reply}</p>
                      )}
                      {!c.generated_reply && c.reply_status === 'pending' && (
                        <button className={styles.actionBtn} onClick={() => handleGenerateReply(c.id)}>
                          Generate Reply
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* Reply review queue */}
      {tab === 'replies' && (
        <div className={styles.repliesSection}>
          {pendingComments.length === 0 ? (
            <div className={styles.emptyState}>
              <p className={styles.emptyTitle}>No pending replies</p>
              <p className={styles.emptySubtitle}>All generated replies have been reviewed.</p>
            </div>
          ) : (
            <ul className={styles.replyList}>
              {pendingComments.map(c => (
                <li key={c.id} className={styles.replyItem}>
                  <div className={styles.replyCommentHeader}>
                    <strong>@{c.author_username}</strong>
                    <span className={styles.replyCommentText}>{c.text}</span>
                  </div>
                  <textarea
                    className={styles.replyEditor}
                    value={editingReply[c.id] ?? (c.generated_reply ?? '')}
                    onChange={e => setEditingReply(prev => ({ ...prev, [c.id]: e.target.value }))}
                    rows={2}
                  />
                  {c.safety_flags && !(c.safety_flags as { passed?: boolean }).passed && (
                    <p className={styles.safetyWarning}>
                      Safety flags: {((c.safety_flags as { reasons?: string[] }).reasons ?? []).join(', ')}
                    </p>
                  )}
                  <div className={styles.replyActions}>
                    <button className={styles.approveBtn} onClick={() => handleReview(c.id, 'approve')}>
                      Approve & Post
                    </button>
                    <button className={styles.rejectBtn} onClick={() => handleReview(c.id, 'reject')}>
                      Reject
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Create post modal */}
      {showCreate && (
        <div className={styles.modalOverlay} onClick={e => e.target === e.currentTarget && setShowCreate(false)}>
          <div className={styles.modal}>
            <h2 className={styles.modalTitle}>Generate Instagram Post</h2>

            <label className={styles.label}>Post Type</label>
            <select
              className={styles.select}
              value={createForm.post_type}
              onChange={e => setCreateForm(f => ({ ...f, post_type: e.target.value as PostCreate['post_type'] }))}
            >
              {['image', 'carousel', 'reel', 'story'].map(t => (
                <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
              ))}
            </select>

            <label className={styles.label}>Character (optional)</label>
            <select
              className={styles.select}
              value={createForm.character_id}
              onChange={e => setCreateForm(f => ({ ...f, character_id: e.target.value }))}
            >
              <option value="">No character (brand voice)</option>
              {characters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>

            <label className={styles.label}>Content Brief</label>
            <textarea
              className={styles.textarea}
              placeholder="Describe the post — theme, mood, what to highlight…"
              value={createForm.prompt_context}
              onChange={e => setCreateForm(f => ({ ...f, prompt_context: e.target.value }))}
              rows={4}
            />

            <label className={styles.label}>Media URLs (one per line, optional)</label>
            <textarea
              className={styles.textarea}
              placeholder="https://…"
              value={createForm.media_urls}
              onChange={e => setCreateForm(f => ({ ...f, media_urls: e.target.value }))}
              rows={2}
            />

            <div className={styles.modalActions}>
              <button className={styles.primaryBtn} onClick={handleCreate} disabled={creating || !createForm.prompt_context.trim()}>
                {creating ? 'Generating…' : 'Generate Draft'}
              </button>
              <button className={styles.ghostBtn} onClick={() => setShowCreate(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </main>
  );
}

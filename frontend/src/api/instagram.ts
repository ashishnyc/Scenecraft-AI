import { apiClient } from './client';

export type PostStatus = 'draft' | 'scheduled' | 'posted' | 'failed';
export type PostType = 'image' | 'carousel' | 'reel' | 'story';
export type CommentReplyStatus = 'pending' | 'approved' | 'rejected' | 'posted';

export interface InstagramPost {
  id: string;
  workspace_id: string;
  character_id: string | null;
  post_type: PostType;
  status: PostStatus;
  caption: string | null;
  hashtags: string[];
  media_urls: string[];
  instagram_post_id: string | null;
  scheduled_at: string | null;
  posted_at: string | null;
  engagement_stats: Record<string, number> | null;
  created_at: string;
}

export interface InstagramComment {
  id: string;
  post_id: string;
  instagram_comment_id: string;
  author_username: string;
  text: string;
  reply_status: CommentReplyStatus;
  generated_reply: string | null;
  posted_reply: string | null;
  safety_flags: Record<string, unknown> | null;
}

export interface InstagramDashboard {
  total_posts: number;
  by_status: Record<string, number>;
  total_likes: number;
  total_comments: number;
  pending_reply_reviews: number;
  scheduled_posts: { id: string; caption_preview: string; scheduled_at: string; post_type: string }[];
}

export interface PostCreate {
  workspace_id: string;
  character_id?: string;
  post_type: PostType;
  prompt_context: string;
  media_urls?: string[];
}

export async function fetchInstagramDashboard(workspaceId: string): Promise<InstagramDashboard> {
  const res = await apiClient.get<InstagramDashboard>(`/instagram/workspaces/${workspaceId}/dashboard`);
  return res.data;
}

export async function fetchPosts(workspaceId: string): Promise<InstagramPost[]> {
  const res = await apiClient.get<InstagramPost[]>('/instagram/posts', { params: { workspace_id: workspaceId } });
  return res.data;
}

export async function createPost(body: PostCreate): Promise<InstagramPost> {
  const res = await apiClient.post<InstagramPost>('/instagram/posts', body);
  return res.data;
}

export async function schedulePost(postId: string, scheduledAt: string): Promise<InstagramPost> {
  const res = await apiClient.post<InstagramPost>(`/instagram/posts/${postId}/schedule`, { scheduled_at: scheduledAt });
  return res.data;
}

export async function publishPostNow(postId: string): Promise<InstagramPost> {
  const res = await apiClient.post<InstagramPost>(`/instagram/posts/${postId}/publish`);
  return res.data;
}

export async function deletePost(postId: string): Promise<void> {
  await apiClient.delete(`/instagram/posts/${postId}`);
}

export async function fetchComments(postId: string): Promise<InstagramComment[]> {
  const res = await apiClient.get<InstagramComment[]>(`/instagram/posts/${postId}/comments`);
  return res.data;
}

export async function generateReply(commentId: string): Promise<InstagramComment> {
  const res = await apiClient.post<InstagramComment>(`/instagram/comments/${commentId}/generate-reply`);
  return res.data;
}

export async function reviewReply(
  commentId: string,
  action: 'approve' | 'reject',
  editedReply?: string
): Promise<InstagramComment> {
  const res = await apiClient.put<InstagramComment>(`/instagram/comments/${commentId}/review`, {
    action,
    edited_reply: editedReply,
  });
  return res.data;
}

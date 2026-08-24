/**
 * 论坛模块 API 封装层
 *
 * 设计说明：
 * - 所有请求最终走 coreApi.instance（axios 实例），其响应拦截器已做两件事：
 *   1) response => response.data（剥离 AxiosResponse 外壳，直接返回业务 body）
 *   2) 401 自动 refresh token / 触发 authExpired 弹窗
 * - 因此本文件中的 apiGet/apiPost/apiPut/apiDelete 只需把 axios 的返回值
 *   “解包”成业务类型 T。由于 TS 对拦截器改写后的返回类型无感知，
 *   仍把 instance.get 标注为 Promise<AxiosResponse>，故这里用 `as unknown as T`
 *   做一道显式断言，把运行时已是 body 的结果映射到业务类型。
 * - 错误处理：本层不 try/catch，统一抛给调用方处理（调用方通常用 toast 提示）。
 *   401 鉴权失效已由 core 拦截器全局兜底，无需在此重复处理。
 */
import type {
  CreateCommentPayload,
  CreatePostPayload,
  ForumBoard,
  ForumCommentListItem,
  ForumConnection,
  ForumMessage,
  ForumNotification,
  ForumPost,
  ForumPostDetail,
  ForumProfile,
  FriendRequest,
  PaginatedResponse,
  SortMode,
  TimeOrder,
  UpdatePostPayload,
} from './types'
import coreApi from '@/api/core'

// ─── HTTP helpers ──────────────────────────────
// coreApi.instance 返回的是 axios 包装结果 (AxiosResponseResult)，此处解包为业务 T

/**
 * 发起 GET 请求并解包为业务类型 T。
 * @param path  相对路径（如 '/forum/api/posts'），baseURL 已由 coreApi 配置
 * @param params 查询参数对象，键名建议用后端约定的 snake_case
 */
async function apiGet<T>(path: string, params?: Record<string, any>): Promise<T> {
  // 拦截器已返回 response.data，此处仅做类型断言到 T
  return coreApi.instance.get(path, { params }) as unknown as T
}

/**
 * 发起 POST 请求并解包为业务类型 T。
 * @param body 请求体，会被 coreApi 的 transformRequest 自动 snake_case 化
 */
async function apiPost<T>(path: string, body?: any): Promise<T> {
  return coreApi.instance.post(path, body) as unknown as T
}

/**
 * 发起 PUT 请求并解包为业务类型 T。
 */
async function apiPut<T>(path: string, body?: any): Promise<T> {
  return coreApi.instance.put(path, body) as unknown as T
}

/**
 * 发起 DELETE 请求并解包为业务类型 T。
 */
async function apiDelete<T>(path: string): Promise<T> {
  return coreApi.instance.delete(path) as unknown as T
}

// ─── Posts ──────────────────────────────────────

/**
 * 拉取帖子列表（分页 + 多维筛选）。
 * @param sort       排序模式
 * @param page       页码（从 1 起）
 * @param pageSize   每页条数
 * @param timeOrder  时间正/倒序
 * @param yearMonth  限定年月（如 '2025-07'），null 表示不限
 * @param boardId    限定板块
 * @param authorId   限定作者
 */
export async function fetchPosts(
  sort: SortMode = 'all',
  page = 1,
  pageSize = 20,
  timeOrder: TimeOrder = 'desc',
  yearMonth: string | null = null,
  boardId: string | null = null,
  authorId: string | null = null,
): Promise<PaginatedResponse<ForumPost>> {
  return apiGet('/forum/api/posts', {
    sort,
    page,
    page_size: pageSize,
    time_order: timeOrder,
    // null ?? undefined → undefined，axios 会跳过 undefined 字段不发
    year_month: yearMonth ?? undefined,
    board_id: boardId ?? undefined,
    author_id: authorId ?? undefined,
  })
}

/**
 * 获取单篇帖子详情（含正文、板块、作者等）。
 */
export async function fetchPost(id: string): Promise<ForumPostDetail> {
  return apiGet(`/forum/api/posts/${id}`)
}

/**
 * 创建新帖子。
 * 把前端的 camelCase 字段（boardIds/personaId）映射为后端期望的 snake_case。
 */
export async function createPost(payload: CreatePostPayload): Promise<ForumPost> {
  return apiPost('/forum/api/posts', {
    ...payload,
    board_ids: payload.boardIds ?? undefined,
    board_id: payload.boardId ?? undefined,
    persona_id: payload.personaId ?? undefined,
  })
}

/**
 * 更新帖子，返回包含审核状态/可见性等后端回写的复合结构。
 */
export async function updatePost(
  id: string,
  payload: UpdatePostPayload,
): Promise<{
  success: boolean
  moderationStatus?: string
  moderationReason?: string | null
  visibilityStatus?: string
  boardIds?: string[]
  boards?: ForumBoard[]
}> {
  return apiPut(`/forum/api/posts/${id}`, {
    ...payload,
    board_ids: payload.boardIds ?? undefined,
    persona_id: payload.personaId ?? undefined,
    moderation_status: payload.moderationStatus ?? undefined,
    visibility_status: payload.visibilityStatus ?? undefined,
    moderation_reason: payload.moderationReason ?? undefined,
  })
}

/**
 * 删除帖子。
 */
export async function deletePost(id: string): Promise<{ success: boolean }> {
  return apiDelete(`/forum/api/posts/${id}`)
}

// ─── Comments ──────────────────────────────────

/**
 * 创建评论。返回值可能附带 friendRequestId：当评论触发“互为好友”逻辑时由后端回写。
 */
export async function createComment(payload: CreateCommentPayload): Promise<{ success: boolean, comment: any, friendRequestId?: string }> {
  return apiPost(`/forum/api/posts/${payload.postId}/comments`, payload)
}

/**
 * 删除评论。
 */
export async function deleteComment(id: string): Promise<{ success: boolean }> {
  return apiDelete(`/forum/api/comments/${id}`)
}

/**
 * 拉取评论列表（可按作者过滤 + 分页）。
 */
export async function fetchComments(
  authorId?: string,
  page = 1,
  pageSize = 20,
): Promise<PaginatedResponse<ForumCommentListItem>> {
  return apiGet('/forum/api/comments', {
    author_id: authorId,
    page,
    page_size: pageSize,
  })
}

// ─── Likes ─────────────────────────────────────

/**
 * 点赞帖子，返回最新点赞数与当前用户是否已赞。
 */
export async function likePost(id: string): Promise<{ likes: number, liked: boolean }> {
  return apiPost(`/forum/api/posts/${id}/like`)
}

/**
 * 点赞评论。
 */
export async function likeComment(id: string): Promise<{ likes: number, liked: boolean }> {
  return apiPost(`/forum/api/comments/${id}/like`)
}

// ─── Boards ────────────────────────────────────

/**
 * 拉取全部板块。
 */
export async function fetchBoards(): Promise<{ items: ForumBoard[] }> {
  return apiGet('/forum/api/boards')
}

// ─── Profile ───────────────────────────────────

/**
 * 获取当前登录用户在论坛的资料。
 */
export async function fetchProfile(): Promise<ForumProfile> {
  return apiGet('/forum/api/profile')
}

/**
 * 更新当前用户资料（部分字段可选）。
 */
export async function updateProfile(
  payload: Partial<Pick<ForumProfile, 'displayName' | 'bio' | 'avatar' | 'contactInfo' | 'interests'> & { autoEvaluate: boolean }>,
): Promise<{ success: boolean }> {
  return apiPut('/forum/api/profile', payload)
}

// ─── Friend Requests ───────────────────────────

/**
 * 拉取好友申请列表。
 * @param status    申请状态过滤
 * @param direction received=我收到的 / sent=我发出的
 */
export async function fetchFriendRequests(
  status?: 'pending' | 'accepted' | 'declined',
  direction: 'received' | 'sent' = 'received',
): Promise<{ items: FriendRequest[] }> {
  return apiGet('/forum/api/friend-requests', { status, direction })
}

/**
 * 接受好友申请。
 */
export async function acceptFriendRequest(requestId: string): Promise<{ success: boolean }> {
  return apiPost(`/forum/api/friend-request/${requestId}/accept`)
}

/**
 * 拒绝好友申请。
 */
export async function declineFriendRequest(requestId: string): Promise<{ success: boolean }> {
  return apiPost(`/forum/api/friend-request/${requestId}/decline`)
}

// ─── Connections (Friends) ─────────────────────

/**
 * 拉取已建立的好友关系列表。
 */
export async function fetchConnections(): Promise<{ items: ForumConnection[] }> {
  return apiGet('/forum/api/connections')
}

// ─── Messages ──────────────────────────────────

/**
 * 拉取私信列表（分页 + 仅未读过滤），返回总数与未读数。
 */
export async function fetchMessages(
  page = 1,
  pageSize = 20,
  unreadOnly = false,
): Promise<{ items: ForumMessage[], total: number, unreadCount: number }> {
  return apiGet('/forum/api/messages', {
    page,
    page_size: pageSize,
    unread_only: unreadOnly,
  })
}

/**
 * 发送私信。postId 可选，用于“在帖子下私聊作者”场景的上下文关联。
 */
export async function sendMessage(
  toUserId: string,
  content: string,
  postId?: string,
): Promise<{ success: boolean, messageId: string }> {
  return apiPost('/forum/api/messages', { toUserId, content, postId })
}

// ─── Notifications ─────────────────────────────

/**
 * 拉取通知列表（分页 + 未读过滤）。
 */
export async function fetchNotifications(
  page = 1,
  pageSize = 20,
  unread?: boolean,
): Promise<{ items: ForumNotification[], total: number, unreadCount: number }> {
  return apiGet('/forum/api/notifications', {
    page,
    page_size: pageSize,
    unread,
  })
}

/**
 * 标记单条通知为已读。
 */
export async function markNotificationRead(id: string): Promise<{ success: boolean }> {
  return apiPost(`/forum/api/notifications/${id}/read`)
}

/**
 * 一键全部已读。
 */
export async function markAllNotificationsRead(): Promise<{ success: boolean }> {
  return apiPost('/forum/api/notifications/read-all')
}

// ─── Report ────────────────────────────────────

/**
 * 举报帖子或评论。
 * @param targetType  'post' | 'comment'
 * @param targetId    被举报对象 ID
 * @param reason      举报理由（分类）
 * @param description 详细描述
 */
export async function reportContent(
  targetType: 'post' | 'comment',
  targetId: string,
  reason?: string,
  description?: string,
): Promise<{ success: boolean, reportId: string }> {
  return apiPost('/forum/api/report', { targetType, targetId, reason, description })
}

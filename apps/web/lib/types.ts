/* Espelho dos schemas da API v1 (services/engine/stark_engine/models.py + schemas.py). */
export type VideoRow = {
  id: number; title: string; origin: "upload" | "library" | "youtube_ref"; youtube_id: string | null;
  url: string | null; thumbnail_url: string | null; channel: string | null; niche: string; duration_s: number;
  width: number; height: number; fps: number; has_audio: boolean; size_bytes: number; status: string;
  error: string | null; favorite: boolean; created_at: string; has_file: boolean; rights_ok: boolean;
};
export type Rights = {
  id: number; rights_type: string; holder: string; evidence: string; allows_edit: boolean;
  allows_commercial: boolean; expires_at: string | null; declared_at: string;
};
export type Candidate = {
  id: number; video_id: number; rank: number; start_s: number; end_s: number; duration_s: number; title: string;
  summary: string; justification: string; hook: string; score: number; score_breakdown: Record<string, number>;
  keywords: string[]; transcript_text: string; source: string; status: "candidate" | "approved" | "rejected";
};
export type CopyText = {
  title?: string; captions?: Record<string, string>; hashtags?: Record<string, string[]>; source?: string;
};
export type Clip = {
  id: number; candidate_id: number; video_id: number; start_s: number; end_s: number; layout: string;
  remove_pauses: boolean; denoise: boolean; logo: boolean; caption_style: Record<string, unknown>;
  words_override: Word[]; status: "draft" | "rendering" | "ready" | "error"; error: string | null;
  duration_s: number; layout_used: string | null; copy_text: CopyText; updated_at: string; files: string[];
};
export type JobRow = {
  id: number; kind: "analyze" | "render" | "publish"; ref_id: number; status: string; stage: string;
  progress: number; attempts: number; max_attempts: number; error: string | null; payload: Record<string, unknown>;
  result: Record<string, unknown>; created_at: string; started_at: string | null; finished_at: string | null;
};
export type VideoDetail = {
  video: VideoRow; rights: Rights[]; candidates: Candidate[]; clips: Clip[]; jobs: JobRow[];
  transcript: { language: string; model: string; words: number; text: string; segments: [number, number, string][] } | null;
};
export type Word = [number, number, string, number?];
export type UploadSession = { upload_id: string; chunk_size: number; chunks: number };
export type ClipContext = {
  words: Word[]; video: { id: number; title: string; duration_s: number; width: number; height: number; niche: string };
  candidate: { id: number; title: string; score: number; justification: string; start_s: number; end_s: number } | null;
  caption_defaults: CaptionStyle;
};
export type CaptionStyle = {
  font: string; size: number; primary: string; highlight: string; outline: string; outline_w: number;
  position: number; words_per_line: number; uppercase: boolean;
};
export type Account = {
  id: number; platform: Platform; handle: string; display_name: string; niche: string; bio: string;
  niche_hashtags: string[]; daily_cap: number; status: string; created_at: string;
};
export type Platform = "tiktok" | "instagram" | "facebook" | "youtube";
export type Post = {
  id: number; edited_clip_id: number; account_id: number; platform: Platform; title: string; caption: string;
  hashtags: string[]; scheduled_at: string; mode: "assisted" | "export" | "api"; status: string; approved: boolean;
  external_url: string | null; error: string | null; created_at: string; published_at: string | null;
  export_dir: string | null; account_handle: string; clip_title: string; upload_url: string | null;
};
export type Stats = {
  videos: { total: number; analyzed: number; by_status: Record<string, number> };
  clips: { candidates: number; awaiting_approval: number; approved: number; edited: number; rendering: number; ready: number };
  jobs: { active: number; last24h: Record<string, number> };
  posts: { by_status: Record<string, number>; scheduled: number; done: number };
  analytics: { posts_with_data: number; views: number; likes: number; comments: number; shares: number;
    followers: number; revenue_confirmed: number };
  ai: { month_spend_usd: number; budget_usd: number; calls_month: number; providers_enabled: string[] };
  storage_mb: number; alerts: string[];
};
export type Health = { ok: boolean; version: string; ffmpeg: boolean; db: boolean; whisper_model: string; youtube_api: boolean };
export type ProviderStatus = {
  provider: string; enabled: boolean; has_key: boolean; model: string; paid: boolean; blocked: boolean; free_tier: boolean;
  price_in: number; price_out: number;
};
export type Settings = {
  autonomy: "assisted" | "semi" | "autonomous"; paused: boolean;
  clips: { target: number; mode: "short" | "long"; min_score: number };
  ai: { monthly_budget_usd: number; hard_limit: boolean; alert_pct: number;
    routing: { cut_planning: string; copywriting: string };
    providers: Record<string, { enabled: boolean; model: string; price_in: number; price_out: number }> };
  captions: CaptionStyle;
  branding: { logo_path: string | null; logo_opacity: number; logo_scale: number };
  cadence: { min_gap_minutes: number; quiet_start: number; quiet_end: number; tz_offset_h: number };
  radar: { enabled: boolean; game: string; languages: string[]; max_channels: number; sensitivity: number;
    min_rate: number; youtube_query: string; watch_twitch: string[]; youtube_channels: string[] };
  inbox: { enabled: boolean; path: string; confirmed: boolean; confirmed_at: string | null; rights_type: string;
    holder: string; allows_commercial: boolean; layout: string; credit: string };
};
export type SettingsResp = { settings: Settings; providers: ProviderStatus[]; env: { youtube_api: boolean; whisper_model: string; free_only: boolean } };
export type Trend = {
  id: number; source: string; region: string; kind: string; label: string; url: string | null;
  metric: Record<string, unknown>; confidence: number; license_note: string; fetched_at: string;
};
export type YtResult = {
  youtube_id: string; title: string; channel: string; published_at: string; thumbnail_url: string;
  duration_s: number; views: number; likes: number; comments: number; license: string; url: string;
};

/* Máquina de clipes (radar) */
export type LiveStatus = {
  radar_running: boolean; chat: string; chat_channels: number; twitch_api: string; youtube_api: string;
  twitch_configured: boolean; youtube_configured: boolean; twitch_connected: boolean; twitch_login: string | null;
  lives: number; viewers: number; moments_today: number; clips_ready: number; game: string | null;
  keyless: boolean; youtube_rss: string; watching: number; chat_rate: number;
  inbox: { status?: string; imported?: number; error?: string };
};
export type LiveRow = {
  id: number; platform: "twitch" | "youtube"; channel: string; display_name: string; title: string; viewers: number;
  game: string; language: string; thumbnail_url: string; url: string; live: boolean; seen_at: string; authorized: boolean;
  chat_rate: number;
};
export type MomentRow = {
  id: number; platform: string; channel: string; at: string; rate: number; baseline: number; score: number; viewers: number;
  tokens: string[]; samples: string[]; status: string; clip_id: string | null; video_id: number | null; error: string | null;
  authorized: boolean; watch_url: string;
};
export type ChannelRow = {
  id: number; platform: string; channel: string; display_name: string; rights_type: string; evidence: string;
  allows_commercial: boolean; auto_clip: boolean; active: boolean; created_at: string;
};
export type HotVideo = {
  id: number; title: string; url: string; channel: string; views: number; views_per_hour: number; thumbnail_url: string;
  duration_s: number; likes: number; published_at: string | null; short: boolean; source: "youtube_rss" | "youtube_api";
};
export type InboxStatus = {
  path: string; exists: boolean; enabled: boolean; confirmed: boolean; confirmed_at: string | null; rights_type: string;
  holder: string; pending: { name: string; size_mb: number; copying: boolean }[]; imported: number;
  errors: { title: string; error: string | null }[];
};
export type QueueItem = { id: number; kind: string; status: string; progress: number; stage: string; label: string; title: string };
export type FeedItem = { clip: Clip; video_id: number; title: string; origin: string; channel: string | null; source_url: string | null };

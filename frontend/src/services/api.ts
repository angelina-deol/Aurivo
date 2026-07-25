const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

interface RequestOptions extends RequestInit {
  token?: string | null;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { token, headers, ...rest } = options;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_active: boolean;
  is_verified: boolean;
}

export const authApi = {
  register: (email: string, password: string, fullName?: string) =>
    request<UserResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
    }),

  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logout: (token: string) =>
    request<void>("/auth/logout", { method: "POST", token }),

  me: (token: string) => request<UserResponse>("/auth/me", { token }),

  // Not a fetch call — this is a full browser navigation to the backend,
  // which redirects on to Google's consent screen.
  googleLoginUrl: () => `${API_BASE_URL}/auth/google/login`,
};

export interface AudioMetadataResponse {
  original_filename: string;
  content_type: string;
  duration_seconds: number;
  sample_rate: number;
  channels: number;
  file_size_bytes: number;
  noise_level: number | null;
  speech_duration_seconds: number | null;
  silence_ratio: number | null;
  has_spectrogram: boolean;
}

export interface InvestigationResponse {
  id: string;
  filename: string;
  status: string;
  prediction: string | null;
  confidence: number | null;
  fraud_score: number | null;
  processing_time_seconds: number | null;
  created_at: string;
  updated_at: string;
  audio_metadata: AudioMetadataResponse | null;
}

export interface InvestigationListResponse {
  items: InvestigationResponse[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * Multipart upload needs its own fetch call — `request()` always sets
 * Content-Type: application/json, which would break the multipart boundary.
 */
async function uploadFile(token: string, file: File): Promise<InvestigationResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/investigations/analyze`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Upload failed with status ${response.status}`);
  }

  return response.json();
}

export const investigationsApi = {
  analyze: (token: string, file: File) => uploadFile(token, file),

  list: (token: string, limit = 20, offset = 0) =>
    request<InvestigationListResponse>(`/investigations?limit=${limit}&offset=${offset}`, {
      token,
    }),

  get: (token: string, id: string) =>
    request<InvestigationResponse>(`/investigations/${id}`, { token }),

  remove: (token: string, id: string) =>
    request<void>(`/investigations/${id}`, { method: "DELETE", token }),

  /**
   * Both the raw audio and the spectrogram image require the auth header,
   * so a plain <audio src="..."> or <img src="..."> won't work — the
   * browser doesn't attach Authorization headers to those. Fetch the bytes
   * ourselves and hand back an object URL instead.
   */
  audioBlobUrl: async (token: string, id: string): Promise<string> => {
    const response = await fetch(`${API_BASE_URL}/investigations/${id}/audio`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error(`Could not load audio (status ${response.status})`);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  },

  spectrogramBlobUrl: async (token: string, id: string): Promise<string | null> => {
    const response = await fetch(`${API_BASE_URL}/investigations/${id}/spectrogram`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.status === 404) return null; // not generated (yet, or generation failed)
    if (!response.ok) throw new Error(`Could not load spectrogram (status ${response.status})`);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  },
};

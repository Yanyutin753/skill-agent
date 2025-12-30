import apiClient from './api';

export interface CommunicationStyle {
  tone: string;
  verbosity: string;
  language: string;
}

export interface UserProfile {
  name?: string;
  role?: string;
  expertise_level: string;
  industry?: string;
}

export interface TechPreferences {
  preferred_languages: string[];
  preferred_frameworks: string[];
  coding_style?: string;
}

export interface PersonalizationSettings {
  user_id: string;
  style: CommunicationStyle;
  profile: UserProfile;
  tech: TechPreferences;
  custom_instructions?: string;
}

export interface StylePreset {
  name: string;
  description: string;
  style: CommunicationStyle;
}

export interface RolePreset {
  name: string;
  expertise_level: string;
}

export interface Presets {
  styles: Record<string, StylePreset>;
  roles: Record<string, RolePreset>;
}

export const defaultSettings: PersonalizationSettings = {
  user_id: 'default-user',
  style: {
    tone: '专业',
    verbosity: '适中',
    language: '中文',
  },
  profile: {
    expertise_level: '中级',
  },
  tech: {
    preferred_languages: [],
    preferred_frameworks: [],
  },
};

export async function getPersonalization(userId: string): Promise<PersonalizationSettings> {
  try {
    const response = await apiClient.get(`/personalization/settings/${userId}`);
    if (response.data.success && response.data.settings) {
      return response.data.settings;
    }
    return { ...defaultSettings, user_id: userId };
  } catch {
    return { ...defaultSettings, user_id: userId };
  }
}

export async function savePersonalization(settings: PersonalizationSettings): Promise<boolean> {
  try {
    const response = await apiClient.post('/personalization/settings', settings);
    return response.data.success;
  } catch {
    return false;
  }
}

export async function resetPersonalization(userId: string): Promise<boolean> {
  try {
    const response = await apiClient.delete(`/personalization/settings/${userId}`);
    return response.data.success;
  } catch {
    return false;
  }
}

export async function getPresets(): Promise<Presets> {
  try {
    const response = await apiClient.get('/personalization/presets');
    return response.data;
  } catch {
    return {
      styles: {},
      roles: {},
    };
  }
}

import { useState, useEffect } from 'react';
import { X, User, Palette, Code, MessageSquare, RotateCcw, Check } from 'lucide-react';
import type {
  PersonalizationSettings,
  CommunicationStyle,
  UserProfile,
  TechPreferences,
  StylePreset,
  RolePreset,
} from '@/services/personalization';
import {
  getPersonalization,
  savePersonalization,
  resetPersonalization,
  getPresets,
  defaultSettings,
} from '@/services/personalization';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  userId: string;
}

type TabType = 'style' | 'profile' | 'tech' | 'custom';

const LANGUAGES = ['TypeScript', 'Python', 'JavaScript', 'Go', 'Rust', 'Java', 'C++', 'Swift'];
const FRAMEWORKS = ['React', 'Vue', 'Next.js', 'FastAPI', 'Django', 'Express', 'Spring', 'Flutter'];

export default function PersonalizationModal({ isOpen, onClose, userId }: Props) {
  const [activeTab, setActiveTab] = useState<TabType>('style');
  const [settings, setSettings] = useState<PersonalizationSettings>({ ...defaultSettings, user_id: userId });
  const [stylePresets, setStylePresets] = useState<Record<string, StylePreset>>({});
  const [rolePresets, setRolePresets] = useState<Record<string, RolePreset>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen, userId]);

  const loadData = async () => {
    const [loadedSettings, presets] = await Promise.all([
      getPersonalization(userId),
      getPresets(),
    ]);
    setSettings(loadedSettings);
    setStylePresets(presets.styles);
    setRolePresets(presets.roles);
  };

  const handleSave = async () => {
    setSaving(true);
    const success = await savePersonalization(settings);
    setSaving(false);
    if (success) {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }
  };

  const handleReset = async () => {
    if (confirm('确定要重置所有个性化设置吗？')) {
      await resetPersonalization(userId);
      setSettings({ ...defaultSettings, user_id: userId });
    }
  };

  const updateStyle = (updates: Partial<CommunicationStyle>) => {
    setSettings(prev => ({
      ...prev,
      style: { ...prev.style, ...updates },
    }));
  };

  const updateProfile = (updates: Partial<UserProfile>) => {
    setSettings(prev => ({
      ...prev,
      profile: { ...prev.profile, ...updates },
    }));
  };

  const updateTech = (updates: Partial<TechPreferences>) => {
    setSettings(prev => ({
      ...prev,
      tech: { ...prev.tech, ...updates },
    }));
  };

  const applyStylePreset = (presetKey: string) => {
    const preset = stylePresets[presetKey];
    if (preset) {
      updateStyle(preset.style);
    }
  };

  const applyRolePreset = (preset: RolePreset) => {
    updateProfile({
      role: preset.name,
      expertise_level: preset.expertise_level,
    });
  };

  const toggleArrayItem = (array: string[], item: string): string[] => {
    return array.includes(item)
      ? array.filter(i => i !== item)
      : [...array, item];
  };

  if (!isOpen) return null;

  const tabs = [
    { id: 'style' as const, label: '风格', icon: Palette },
    { id: 'profile' as const, label: '角色', icon: User },
    { id: 'tech' as const, label: '技术', icon: Code },
    { id: 'custom' as const, label: '指令', icon: MessageSquare },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">个性化设置</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-full transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-100 px-6">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-black text-black'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'style' && (
            <div className="space-y-6">
              {/* Style Presets */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">快捷预设</label>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(stylePresets).map(([key, preset]) => (
                    <button
                      key={key}
                      onClick={() => applyStylePreset(key)}
                      className="p-3 text-left border border-gray-200 rounded-lg hover:border-gray-300 hover:bg-gray-50 transition-colors"
                    >
                      <div className="font-medium text-gray-900">{preset.name}</div>
                      <div className="text-xs text-gray-500 mt-1">{preset.description}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Tone */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">沟通风格</label>
                <div className="flex flex-wrap gap-2">
                  {['专业', '随意', '友好', '正式'].map(value => (
                    <button
                      key={value}
                      onClick={() => updateStyle({ tone: value })}
                      className={`px-4 py-2 rounded-full text-sm transition-colors ${
                        settings.style.tone === value
                          ? 'bg-black text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>

              {/* Verbosity */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">回复详细程度</label>
                <div className="flex flex-wrap gap-2">
                  {['简洁', '适中', '详细'].map(value => (
                    <button
                      key={value}
                      onClick={() => updateStyle({ verbosity: value })}
                      className={`px-4 py-2 rounded-full text-sm transition-colors ${
                        settings.style.verbosity === value
                          ? 'bg-black text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>

              {/* Language */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">首选语言</label>
                <div className="flex flex-wrap gap-2">
                  {['中文', '英文', '自动'].map(value => (
                    <button
                      key={value}
                      onClick={() => updateStyle({ language: value })}
                      className={`px-4 py-2 rounded-full text-sm transition-colors ${
                        settings.style.language === value
                          ? 'bg-black text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'profile' && (
            <div className="space-y-6">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">称呼</label>
                <input
                  type="text"
                  value={settings.profile.name || ''}
                  onChange={e => updateProfile({ name: e.target.value })}
                  placeholder="你希望我如何称呼你"
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-black/5 focus:border-gray-300"
                />
              </div>

              {/* Role Presets */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">职业角色</label>
                <div className="grid grid-cols-3 gap-2">
                  {Object.values(rolePresets).map(preset => (
                    <button
                      key={preset.name}
                      onClick={() => applyRolePreset(preset)}
                      className={`p-3 text-center border rounded-lg transition-colors ${
                        settings.profile.role === preset.name
                          ? 'border-black bg-black/5'
                          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      <div className="font-medium text-gray-900">{preset.name}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Expertise Level */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">技术水平</label>
                <div className="flex flex-wrap gap-2">
                  {['入门', '中级', '专家'].map(value => (
                    <button
                      key={value}
                      onClick={() => updateProfile({ expertise_level: value })}
                      className={`px-4 py-2 rounded-full text-sm transition-colors ${
                        settings.profile.expertise_level === value
                          ? 'bg-black text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>

              {/* Industry */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">所属行业</label>
                <input
                  type="text"
                  value={settings.profile.industry || ''}
                  onChange={e => updateProfile({ industry: e.target.value })}
                  placeholder="例如: 互联网、金融、教育"
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-black/5 focus:border-gray-300"
                />
              </div>
            </div>
          )}

          {activeTab === 'tech' && (
            <div className="space-y-6">
              {/* Preferred Languages */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">偏好编程语言</label>
                <div className="flex flex-wrap gap-2">
                  {LANGUAGES.map(lang => (
                    <button
                      key={lang}
                      onClick={() => updateTech({
                        preferred_languages: toggleArrayItem(settings.tech.preferred_languages, lang),
                      })}
                      className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                        settings.tech.preferred_languages.includes(lang)
                          ? 'bg-black text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {lang}
                    </button>
                  ))}
                </div>
              </div>

              {/* Preferred Frameworks */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">偏好框架</label>
                <div className="flex flex-wrap gap-2">
                  {FRAMEWORKS.map(fw => (
                    <button
                      key={fw}
                      onClick={() => updateTech({
                        preferred_frameworks: toggleArrayItem(settings.tech.preferred_frameworks, fw),
                      })}
                      className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                        settings.tech.preferred_frameworks.includes(fw)
                          ? 'bg-black text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {fw}
                    </button>
                  ))}
                </div>
              </div>

              {/* Coding Style */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">编码风格偏好</label>
                <input
                  type="text"
                  value={settings.tech.coding_style || ''}
                  onChange={e => updateTech({ coding_style: e.target.value })}
                  placeholder="例如: 函数式编程、OOP、简洁优先"
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-black/5 focus:border-gray-300"
                />
              </div>
            </div>
          )}

          {activeTab === 'custom' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  自定义指令
                </label>
                <p className="text-sm text-gray-500 mb-3">
                  告诉 AI 你希望它如何回应，这些指令会应用到所有对话中。
                </p>
                <textarea
                  value={settings.custom_instructions || ''}
                  onChange={e => setSettings(prev => ({ ...prev, custom_instructions: e.target.value }))}
                  placeholder="例如：&#10;- 回复时先给出结论再解释&#10;- 代码示例使用 TypeScript&#10;- 避免使用过于复杂的术语"
                  rows={8}
                  className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-black/5 focus:border-gray-300 resize-none"
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100 bg-gray-50">
          <button
            onClick={handleReset}
            className="flex items-center gap-2 px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
            重置
          </button>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-5 py-2 bg-black text-white rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50 transition-colors"
            >
              {saved ? (
                <>
                  <Check className="w-4 h-4" />
                  已保存
                </>
              ) : saving ? (
                '保存中...'
              ) : (
                '保存'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

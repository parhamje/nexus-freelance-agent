// Page registry: nav id -> {title(), render(container, params, isCurrent)}
import { overview } from './home.js';
import { projectListPage } from './projects.js';
import { proposals, submitted } from './proposals.js';
import { platforms, telegram, ai } from './integrations.js';
import { agentconfig, profile, notifications, prompts, analytics, logs, settings } from './settings_pages.js';
import { t } from '../i18n.js';

const pl = (key) => {
  const page = projectListPage(key);
  return { ...page, title: page.title };
};

export const PAGES = {
  overview: { ...overview, title: overview.title },
  discovered: pl('discovered'),
  recommended: pl('recommended'),
  skipped: pl('skipped'),
  approved: pl('approved'),
  proposals: { ...proposals, title: proposals.title },
  submitted: { ...submitted, title: submitted.title },
  platforms: { ...platforms, title: () => t('platforms') },
  ai: { ...ai, title: () => t('ai') },
  agentconfig: { ...agentconfig, title: () => t('agentconfig') },
  profile: { ...profile, title: () => t('profile') },
  telegram: { ...telegram, title: () => t('telegram') },
  notifications: { ...notifications, title: () => t('notifications') },
  prompts: { ...prompts, title: () => t('prompts') },
  analytics: { ...analytics, title: () => t('analytics') },
  logs: { ...logs, title: () => t('logs') },
  settings: { ...settings, title: () => t('settings') },
};

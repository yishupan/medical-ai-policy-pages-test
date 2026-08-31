import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const POLICY_PATH = 'data/policies.json';
const RUN_PATH = 'data/run.json';
const SITE_DATA_DIR = 'site/data';
const SITE_POLICY_PATH = `${SITE_DATA_DIR}/policies.json`;
const SITE_RUN_PATH = `${SITE_DATA_DIR}/run.json`;
const TIME_ZONE = 'Asia/Shanghai';

function formatZhDateTime(value) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: TIME_ZONE,
    dateStyle: 'medium',
    timeStyle: 'medium'
  }).format(value);
}

function shanghaiDateKey(value) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(value);
  const part = Object.fromEntries(parts.filter(({ type }) => type !== 'literal').map(({ type, value: partValue }) => [type, partValue]));
  return `${part.year}-${part.month}-${part.day}`;
}

function readGit(args) {
  return execFileSync('git', args, {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    maxBuffer: 10 * 1024 * 1024
  }).trim();
}

function collectNewPolicyUrls(currentPayload) {
  try {
    const commits = readGit(['rev-list', '-n', '2', 'HEAD', '--', POLICY_PATH]).split('\n').filter(Boolean);
    if (commits.length < 2) return { newPolicyUrls: new Set(), latestPolicyCommitAt: '' };

    const latestPolicyCommitAt = readGit(['show', '-s', '--format=%cI', commits[0]]);
    if (shanghaiDateKey(new Date(latestPolicyCommitAt)) !== shanghaiDateKey(new Date())) {
      return { newPolicyUrls: new Set(), latestPolicyCommitAt };
    }

    const previousPayload = JSON.parse(readGit(['show', `${commits[1]}:${POLICY_PATH}`]));
    const previousPolicyIds = new Set(previousPayload.policies.map((record) => record.policy_id).filter(Boolean));
    const previousSourceUrls = new Set(previousPayload.policies.map((record) => record.source_url).filter(Boolean));
    const newPolicyUrls = new Set(
      currentPayload.policies
        .filter((record) => {
          const hasSameId = record.policy_id && previousPolicyIds.has(record.policy_id);
          const hasSameSource = record.source_url && previousSourceUrls.has(record.source_url);
          return !hasSameId && !hasSameSource;
        })
        .map((record) => record.source_url)
        .filter(Boolean)
    );
    return { newPolicyUrls, latestPolicyCommitAt };
  } catch (error) {
    console.warn(`warning: unable to derive NEW badges from git history: ${error.message}`);
    return { newPolicyUrls: new Set(), latestPolicyCommitAt: '' };
  }
}

const now = new Date();
const currentPolicies = JSON.parse(await readFile(POLICY_PATH, 'utf8'));
const { newPolicyUrls, latestPolicyCommitAt } = collectNewPolicyUrls(currentPolicies);
const sitePolicies = {
  ...currentPolicies,
  new_policy_count: newPolicyUrls.size,
  policies: currentPolicies.policies.map((record) => ({
    ...record,
    is_new_today: newPolicyUrls.has(record.source_url)
  }))
};

const runPayload = {
  generated_at: formatZhDateTime(now),
  policy_data_generated_at: currentPolicies.generated_at,
  new_policy_count: newPolicyUrls.size
};
if (latestPolicyCommitAt) runPayload.latest_policy_commit_at = latestPolicyCommitAt;

await mkdir('data', { recursive: true });
await mkdir(SITE_DATA_DIR, { recursive: true });
const runJson = JSON.stringify(runPayload, null, 2) + '\n';
await writeFile(RUN_PATH, runJson);
await writeFile(SITE_RUN_PATH, runJson);
await writeFile(SITE_POLICY_PATH, JSON.stringify(sitePolicies, null, 2) + '\n');

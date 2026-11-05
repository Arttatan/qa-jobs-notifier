export type JobHit = {
  source: string;
  company: string;
  title: string;
  location: string;
  url: string;
  publishedAt: string | null;
  locationCaution: boolean;
};

const TITLE_OK =
  /\bqa\b|quality assurance|quality engineer|test engineer|\bsdet\b|automation tester|software tester|manual tester|qa automation/i;
const TITLE_BLOCK =
  /\b(director|vp|vice president|sales|recruiter|marketer|account partner|copywriter|designer|intern)\b/i;
const REMOTE = /remote|worldwide|anywhere|distributed|work from home/i;
const NOT_REMOTE = /hybrid|on-?site|onsite/i;
const OPEN_REGION =
  /europe|emea|portugal|lisbon|poland|spain|germany|france|netherlands|ireland|italy|romania|bulgaria|serbia|czech|estonia|latvia|lithuania|sweden|norway|denmark|finland|austria|belgium|greece|hungary|croatia|cyprus|worldwide|anywhere|global/i;
const BLOCKED_REGION =
  /india|united states|\busa\b|\bu\.s\.a\b|\bu\.s\.\b|canada|massachusetts|boston|california|new york|texas|seattle|san francisco|chicago|atlanta|washington|latam|latin america|apac|australia|philippines|brazil|mexico|south korea|singapore|japan|china/i;

const GREENHOUSE_BOARDS = [
  "veeamsoftware",
  "jetbrains",
  "remotepeople",
  "shifttechnology",
  "wargamingen",
  "fluxon",
  "proton",
  "vonage",
  "brainrocketltd",
  "medrio",
];

const LEVER_COMPANIES = ["veeva", "openx", "airalo", "walkme"];

type SourceResult = {
  source: string;
  jobs: JobHit[];
  failed: boolean;
};

export function titleFits(title: string): boolean {
  return TITLE_OK.test(title) && !TITLE_BLOCK.test(title);
}

export function locationCaution(location: string): boolean {
  return !OPEN_REGION.test(location);
}

export function keepLocation(location: string): boolean {
  if (OPEN_REGION.test(location)) return true;
  return !BLOCKED_REGION.test(location);
}

export function remoteEnough(text: string): boolean {
  if (NOT_REMOTE.test(text) && !REMOTE.test(text)) return false;
  return REMOTE.test(text);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

async function getJson(url: string, timeoutMs: number): Promise<unknown> {
  const response = await fetch(url, {
    signal: AbortSignal.timeout(timeoutMs),
    headers: { accept: "application/json", "user-agent": "job-apply-copilot" },
  });
  if (!response.ok) {
    throw new Error(String(response.status));
  }
  return response.json() as Promise<unknown>;
}

async function fetchGreenhouse(board: string): Promise<JobHit[]> {
  const payload = asRecord(
    await getJson(`https://boards-api.greenhouse.io/v1/boards/${board}/jobs`, 12_000),
  );
  const rows = payload?.jobs;
  if (!Array.isArray(rows)) return [];
  const jobs: JobHit[] = [];
  for (const row of rows) {
    const job = asRecord(row);
    if (!job) continue;
    const title = asString(job.title);
    const url = asString(job.absolute_url);
    const location = asString(asRecord(job.location)?.name);
    if (!title || !url || !titleFits(title)) continue;
    if (!remoteEnough(`${title} ${location}`) || !keepLocation(location)) continue;
    const publishedAt = asString(job.updated_at) || asString(job.created_at) || null;
    jobs.push({
      source: `greenhouse:${board}`,
      company: board,
      title,
      location,
      url,
      publishedAt,
      locationCaution: locationCaution(location),
    });
  }
  return jobs;
}

async function fetchLever(company: string): Promise<JobHit[]> {
  const payload = await getJson(
    `https://api.lever.co/v0/postings/${company}?mode=json`,
    15_000,
  );
  if (!Array.isArray(payload)) return [];
  const jobs: JobHit[] = [];
  for (const row of payload) {
    const job = asRecord(row);
    if (!job) continue;
    const title = asString(job.text);
    const url = asString(job.hostedUrl);
    const categories = asRecord(job.categories);
    const location = asString(categories?.location);
    const workplace = asString(job.workplaceType);
    if (!title || !url || !titleFits(title)) continue;
    if (!remoteEnough(`${title} ${location} ${workplace}`) || !keepLocation(location)) continue;
    const createdAt = job.createdAt;
    const publishedAt =
      typeof createdAt === "number" && Number.isFinite(createdAt) && createdAt > 0
        ? new Date(createdAt).toISOString()
        : null;
    jobs.push({
      source: `lever:${company}`,
      company,
      title,
      location,
      url,
      publishedAt,
      locationCaution: locationCaution(`${location} ${workplace}`),
    });
  }
  return jobs;
}

async function loadSource(source: string, load: () => Promise<JobHit[]>): Promise<SourceResult> {
  try {
    return { source, jobs: await load(), failed: false };
  } catch {
    return { source, jobs: [], failed: true };
  }
}

export async function searchQaJobs(limit: number): Promise<{
  jobs: JobHit[];
  failedSources: string[];
  scannedSources: number;
}> {
  const tasks = [
    ...GREENHOUSE_BOARDS.map((board) =>
      loadSource(`greenhouse:${board}`, () => fetchGreenhouse(board)),
    ),
    ...LEVER_COMPANIES.map((company) =>
      loadSource(`lever:${company}`, () => fetchLever(company)),
    ),
  ];
  const results = await Promise.all(tasks);
  const seen = new Set<string>();
  const jobs: JobHit[] = [];
  for (const result of results) {
    for (const job of result.jobs) {
      if (seen.has(job.url)) continue;
      seen.add(job.url);
      jobs.push(job);
    }
  }
  jobs.sort((a, b) => {
    if (a.locationCaution !== b.locationCaution) return a.locationCaution ? 1 : -1;
    const aTime = a.publishedAt ? Date.parse(a.publishedAt) : 0;
    const bTime = b.publishedAt ? Date.parse(b.publishedAt) : 0;
    return bTime - aTime;
  });
  return {
    jobs: jobs.slice(0, limit),
    failedSources: results.filter((result) => result.failed).map((result) => result.source),
    scannedSources: results.length,
  };
}

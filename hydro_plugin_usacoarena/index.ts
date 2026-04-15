import {
    Context,
    Handler,
    ProblemModel,
    RecordModel,
    Schema,
    SettingModel,
    SolutionModel,
    SystemModel,
    Types,
    definePlugin,
    post,
    param,
} from 'hydrooj';
import { ObjectId } from 'mongodb';

type ProblemDocLike = Record<string, any>;
type RecordDocLike = Record<string, any>;

const TAG_PREFIX = 'usacoarena-problem-id:';
const DEFAULT_API_BASE = '/usacoarena/api';

function getPluginBase() {
    const configured = (SystemModel.get('usacoarenaHydro.apiBase') || DEFAULT_API_BASE).trim();
    const normalized = configured.startsWith('/') ? configured : `/${configured}`;
    return normalized.replace(/\/+$/, '');
}

function getExpectedToken() {
    return String(SystemModel.get('usacoarenaHydro.apiToken') || '').trim();
}

function normalizeLongProblemId(problemId: string) {
    return String(problemId || '').trim();
}

function extractAliasFromTags(tags: unknown): string | null {
    if (!Array.isArray(tags)) return null;
    for (const tag of tags) {
        const text = String(tag || '').trim();
        if (text.startsWith(TAG_PREFIX)) return text.slice(TAG_PREFIX.length);
    }
    return null;
}

function parseLevel(tags: unknown): string {
    if (!Array.isArray(tags)) return 'bronze';
    const levels = new Set(['bronze', 'silver', 'gold', 'platinum']);
    for (const tag of tags) {
        const text = String(tag || '').trim().toLowerCase();
        if (levels.has(text)) return text;
    }
    return 'bronze';
}

function parseLimitToMs(raw: unknown, fallbackMs: number): number {
    const text = String(raw || '').trim().toLowerCase();
    if (!text) return fallbackMs;
    if (text.endsWith('ms')) {
        const value = Number(text.slice(0, -2));
        return Number.isFinite(value) ? Math.max(1, Math.floor(value)) : fallbackMs;
    }
    if (text.endsWith('s')) {
        const value = Number(text.slice(0, -1));
        return Number.isFinite(value) ? Math.max(1, Math.floor(value * 1000)) : fallbackMs;
    }
    const value = Number(text);
    return Number.isFinite(value) ? Math.max(1, Math.floor(value)) : fallbackMs;
}

function parseMemoryToMb(raw: unknown, fallbackMb: number): number {
    const text = String(raw || '').trim().toLowerCase();
    if (!text) return fallbackMb;
    if (text.endsWith('mb') || text.endsWith('m')) {
        const value = Number(text.replace(/m(?:b)?$/, ''));
        return Number.isFinite(value) ? Math.max(1, Math.floor(value)) : fallbackMb;
    }
    if (text.endsWith('kb') || text.endsWith('k')) {
        const value = Number(text.replace(/k(?:b)?$/, ''));
        return Number.isFinite(value) ? Math.max(1, Math.floor(value / 1024)) : fallbackMb;
    }
    const value = Number(text);
    return Number.isFinite(value) ? Math.max(1, Math.floor(value)) : fallbackMb;
}

function parseSamples(statement: string) {
    const text = String(statement || '');
    const inputMatch = text.match(/SAMPLE INPUT:\s*([\s\S]*?)SAMPLE OUTPUT:/i);
    const outputMatch = text.match(/SAMPLE OUTPUT:\s*([\s\S]*?)(?:\n[A-Z][A-Z ]+:|\nProblem credits:|$)/i);
    if (!inputMatch || !outputMatch) return [];
    return [{
        id: 'sample_1',
        input_data: inputMatch[1].trim(),
        expected_output: outputMatch[1].trim(),
    }];
}

function summarizeProblem(pdoc: ProblemDocLike) {
    const config = typeof pdoc.config === 'object' && pdoc.config ? pdoc.config : {};
    const alias = extractAliasFromTags(pdoc.tag) || null;
    const statement = String(pdoc.content || '');
    return {
        id: alias || pdoc.pid || String(pdoc.docId),
        hydro_doc_id: pdoc.docId,
        hydro_pid: pdoc.pid || null,
        alias_problem_id: alias,
        title: String(pdoc.title || ''),
        description: statement,
        statement,
        level: parseLevel(pdoc.tag),
        tags: Array.isArray(pdoc.tag) ? pdoc.tag.map((v) => String(v)) : [],
        sample_cases: parseSamples(statement),
        time_limit_ms: parseLimitToMs(config.time, 1000),
        memory_limit_mb: parseMemoryToMb(config.memory, 256),
        test_case_count: Array.isArray(config.cases) ? config.cases.length : 0,
        supported_languages: Array.isArray(config.langs)
            ? config.langs.map((v: unknown) => String(v))
            : [],
    };
}

async function resolveProblemDoc(domainId: string, problemId: string) {
    const normalized = normalizeLongProblemId(problemId);
    if (!normalized) return null;
    const direct = await ProblemModel.get(domainId, normalized);
    if (direct) return direct;

    const docs = await ProblemModel.getMulti(domainId, {}).toArray();
    for (const doc of docs) {
        const alias = extractAliasFromTags(doc.tag);
        if (alias === normalized) return doc;
    }
    return null;
}

function isFinishedStatus(status: unknown) {
    return ![9, 10, 11, 12].includes(Number(status));
}

function authFailed(handler: Handler) {
    handler.response.status = 401;
    handler.response.body = { ok: false, error: 'Unauthorized' };
}

class USACOArenaApiHandler extends Handler {
    noCheckPermView = true;

    async ensureAuthorized() {
        const expected = getExpectedToken();
        if (!expected) return true;
        const header = String(
            this.request.headers.authorization
            || this.request.headers['x-usacoarena-token']
            || '',
        ).trim();
        const bearer = header.startsWith('Bearer ') ? header.slice(7).trim() : header;
        if (bearer === expected) return true;
        authFailed(this);
        return false;
    }
}

class HealthHandler extends USACOArenaApiHandler {
    async get() {
        if (!await this.ensureAuthorized()) return;
        this.response.body = {
            ok: true,
            data: {
                connected: true,
                plugin: '@usacoarena/hydro-plugin',
            },
        };
    }
}

class ProblemListHandler extends USACOArenaApiHandler {
    async get(domainId: string) {
        if (!await this.ensureAuthorized()) return;
        const docs = await ProblemModel.getMulti(domainId, {}).toArray();
        const level = String(this.args.level || '').trim().toLowerCase();
        const detail = String(this.args.detail || '').trim().toLowerCase();
        let rows = docs.map((doc) => summarizeProblem(doc));
        if (level) rows = rows.filter((row) => row.level === level);
        if (detail !== 'full') {
            rows = rows.map((row) => ({
                id: row.id,
                title: row.title,
                level: row.level,
                time_limit_ms: row.time_limit_ms,
                memory_limit_mb: row.memory_limit_mb,
                sample_count: row.sample_cases.length,
                test_case_count: row.test_case_count,
            }));
        }
        this.response.body = { ok: true, data: rows };
    }
}

class ResolveProblemHandler extends USACOArenaApiHandler {
    @param('problem_id', Types.String)
    async get(domainId: string, problemId: string) {
        if (!await this.ensureAuthorized()) return;
        const pdoc = await resolveProblemDoc(domainId, problemId);
        if (!pdoc) {
            this.response.status = 404;
            this.response.body = { ok: false, error: `Problem not found: ${problemId}` };
            return;
        }
        this.response.body = {
            ok: true,
            data: {
                requested_problem_id: normalizeLongProblemId(problemId),
                resolved: summarizeProblem(pdoc),
            },
        };
    }
}

class ProblemDetailHandler extends USACOArenaApiHandler {
    @param('problemId', Types.String)
    async get(domainId: string, problemId: string) {
        if (!await this.ensureAuthorized()) return;
        const pdoc = await resolveProblemDoc(domainId, problemId);
        if (!pdoc) {
            this.response.status = 404;
            this.response.body = { ok: false, error: `Problem not found: ${problemId}` };
            return;
        }
        this.response.body = { ok: true, data: summarizeProblem(pdoc) };
    }
}

class ProblemSolutionHandler extends USACOArenaApiHandler {
    @param('problemId', Types.String)
    async get(domainId: string, problemId: string) {
        if (!await this.ensureAuthorized()) return;
        const pdoc = await resolveProblemDoc(domainId, problemId);
        if (!pdoc) {
            this.response.status = 404;
            this.response.body = { ok: false, error: `Problem not found: ${problemId}` };
            return;
        }
        const cursor = SolutionModel.getMulti(domainId, pdoc.docId);
        const rows = await cursor.limit(1).toArray();
        if (!rows.length) {
            this.response.status = 404;
            this.response.body = { ok: false, error: 'Solution not found' };
            return;
        }
        this.response.body = {
            ok: true,
            data: {
                content: String(rows[0].content || ''),
            },
        };
    }
}

class SubmissionHandler extends USACOArenaApiHandler {
    @post('problem_id', Types.String)
    @post('language', Types.String)
    @post('code', Types.String)
    async post(domainId: string, problemId: string, language: string, code: string) {
        if (!await this.ensureAuthorized()) return;
        const pdoc = await resolveProblemDoc(domainId, problemId);
        if (!pdoc) {
            this.response.status = 404;
            this.response.body = { ok: false, error: `Problem not found: ${problemId}` };
            return;
        }
        const rid = await RecordModel.add(
            domainId,
            pdoc.docId,
            this.user._id,
            language,
            code,
            true,
            { type: 'judge' },
        );
        this.response.body = {
            ok: true,
            data: {
                record_id: rid.toHexString(),
                problem: summarizeProblem(pdoc),
            },
        };
    }
}

class RecordDetailApiHandler extends USACOArenaApiHandler {
    @param('recordId', Types.String)
    async get(domainId: string, recordId: string) {
        if (!await this.ensureAuthorized()) return;
        const rid = new ObjectId(recordId);
        const rdoc = await RecordModel.get(domainId, rid);
        if (!rdoc) {
            this.response.status = 404;
            this.response.body = { ok: false, error: `Record not found: ${recordId}` };
            return;
        }
        this.response.body = {
            ok: true,
            data: {
                record_id: rdoc._id.toHexString(),
                finished: isFinishedStatus(rdoc.status),
                status: rdoc.status,
                score: Number(rdoc.score || 0),
                time_ms: Number(rdoc.time || 0),
                memory_kb: Math.floor(Number(rdoc.memory || 0) / 1024),
                test_cases: Array.isArray(rdoc.testCases)
                    ? rdoc.testCases.map((item: any) => ({
                        id: item.id,
                        status: item.status,
                        score: Number(item.score || 0),
                        time_ms: Number(item.time || 0),
                        memory_kb: Math.floor(Number(item.memory || 0) / 1024),
                        message: item.message || '',
                    }))
                    : [],
                compiler_texts: Array.isArray(rdoc.compilerTexts) ? rdoc.compilerTexts : [],
                judge_texts: Array.isArray(rdoc.judgeTexts) ? rdoc.judgeTexts : [],
            },
        };
    }
}

class PretestHandler extends USACOArenaApiHandler {
    @post('problem_id', Types.String)
    @post('language', Types.String)
    @post('code', Types.String)
    @post('inputs', Types.ArrayOf(Types.String))
    async post(domainId: string, problemId: string, language: string, code: string, inputs: string[]) {
        if (!await this.ensureAuthorized()) return;
        const pdoc = await resolveProblemDoc(domainId, problemId);
        if (!pdoc) {
            this.response.status = 404;
            this.response.body = { ok: false, error: `Problem not found: ${problemId}` };
            return;
        }
        const rid = await RecordModel.add(
            domainId,
            pdoc.docId,
            this.user._id,
            language,
            code,
            true,
            { input: inputs || [], type: 'pretest' },
        );
        const finalRecord = await waitForRecord(domainId, rid);
        this.response.body = {
            ok: true,
            data: {
                record_id: rid.toHexString(),
                finished: true,
                results: Array.isArray(finalRecord.testCases)
                    ? finalRecord.testCases.map((item: any) => ({
                        id: item.id,
                        status: item.status,
                        time_ms: Number(item.time || 0),
                        memory_kb: Math.floor(Number(item.memory || 0) / 1024),
                        stdout: '',
                        stderr: item.message || '',
                    }))
                    : [],
                compiler_texts: Array.isArray(finalRecord.compilerTexts) ? finalRecord.compilerTexts : [],
                judge_texts: Array.isArray(finalRecord.judgeTexts) ? finalRecord.judgeTexts : [],
            },
        };
    }
}

async function waitForRecord(domainId: string, rid: ObjectId, timeoutMs = 120000, intervalMs = 500) {
    const deadline = Date.now() + timeoutMs;
    let latest = await RecordModel.get(domainId, rid);
    while (latest && !isFinishedStatus(latest.status) && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, intervalMs));
        latest = await RecordModel.get(domainId, rid);
    }
    if (!latest) throw new Error(`Record disappeared: ${rid.toHexString()}`);
    return latest;
}

function apply(ctx: Context) {
    ctx.setting.SystemSetting(Schema.object({
        usacoarenaHydro: Schema.object({
            apiToken: Schema.string().role('secret').default('').description('Bearer token for USACOArena Hydro plugin API'),
            apiBase: Schema.string().default(DEFAULT_API_BASE).description('Mounted base path for the USACOArena machine API'),
        }),
    }));

    const base = getPluginBase();
    ctx.Route('usacoarena_hydro_health', `${base}/health`, HealthHandler);
    ctx.Route('usacoarena_hydro_problem_list', `${base}/problems`, ProblemListHandler);
    ctx.Route('usacoarena_hydro_problem_resolve', `${base}/resolve`, ResolveProblemHandler);
    ctx.Route('usacoarena_hydro_problem_detail', `${base}/problems/:problemId`, ProblemDetailHandler);
    ctx.Route('usacoarena_hydro_problem_solution', `${base}/problems/:problemId/solution`, ProblemSolutionHandler);
    ctx.Route('usacoarena_hydro_submission', `${base}/submissions`, SubmissionHandler);
    ctx.Route('usacoarena_hydro_record', `${base}/records/:recordId`, RecordDetailApiHandler);
    ctx.Route('usacoarena_hydro_pretest', `${base}/pretest`, PretestHandler);

    ctx.i18n.load('zh', {
        'USACOArena Hydro Plugin': 'USACOArena Hydro 插件',
    });

    // Touch SettingModel.langs so the plugin fails fast if Hydro language config is broken.
    void SettingModel.langs;
}

export default definePlugin({
    name: '@usacoarena/hydro-plugin',
    apply,
});

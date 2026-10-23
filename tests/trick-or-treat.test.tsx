import type { On, SessionMessage } from 'claude-code'
import { expect, test } from 'claude-code/testing'

const BAND = {
  plugin: 'trick-or-treat',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 3,
    bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 3 },
    view: {},
  },
} as const

const USAGE = {
  input_tokens: 420,
  output_tokens: 31,
  cache_creation_input_tokens: 0,
  cache_read_input_tokens: 0,
}

// The engine beneath the plugin: a fake file system that keeps what is
// written, a fixed session, and a ghost that always says trick.
const engine = (on: On, files: Map<string, string>, prompts: string[]) => {
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: { command: 'ghost' } }))
  on('env.get', () => ({ value: '/home/ghost' }))
  on('session.id', () => ({ value: 'sess-1' }))
  on('session.cwd', () => ({ value: '/repo' }))
  on('fs.exists', (_, e) => ({ value: files.has(e.path) }))
  on('fs.read', (_, e) => ({ value: files.get(e.path) ?? '' }))
  on('fs.write', (_, e) => {
    files.set(e.path, e.text)
    return { value: undefined }
  })
  const messages: SessionMessage[] = [
      { role: 'user', text: 'Fix the login bug', toolUses: [] },
      {
        role: 'assistant',
        text: '',
        toolUses: [{ tool_use_id: 't1', tool: 'Edit', input: { file_path: 'src/auth.ts' }, text: 'The file src/auth.ts has been updated.' }],
      },
      { role: 'user', text: '', toolUses: [], toolResults: [{ tool_use_id: 't1', text: 'ok', isError: false }] },
      { role: 'assistant', text: 'Fixed it, works now.', toolUses: [] },
  ]
  on('session.messages', () => ({ value: messages }))
  on('clock.now', () => ({ value: Date.UTC(2026, 9, 31, 23, 59) }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('model.complete', (_, e) => {
    prompts.push(typeof e.prompt === 'string' ? e.prompt : '')
    return {
      value: {
        isAnswered: true,
        text: '{"verdict":"trick","rule":1,"reason":"You edited src/auth.ts and ran no tests. The ghost of QA past wails."}',
        usage: USAGE,
      },
    }
  })
  on('tool.call', () => ({ result: {} }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })
}

const LOG = '/home/ghost/.claude/trick-or-treat/logs/sess-1.jsonl'

test('the ghost judges a turn, logs it and shows the band', async ($, on) => {
  const files = new Map<string, string>()
  const prompts: string[] = []
  engine(on, files, prompts)
  on('turn.complete', () => ({ text: 'Fixed it, works now.' }))

  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await $.turn.complete({
    turnId: 'turn-1',
    answer: 'Fixed it, works now.',
    durationMs: 4200,
    isAborted: false,
    reason: 'answer',
  })

  expect(prompts[0]).toContain('1. Edit: src/auth.ts')
  expect(prompts[0]).toContain('OUTPUT: The file src/auth.ts has been updated.')

  const record = JSON.parse((files.get(LOG) ?? '').trim())
  expect(record.kind).toBe('verdict')
  expect(record.verdict).toBe('trick')
  expect(record.rule).toBe(1)
  expect(record.session_id).toBe('sess-1')
  expect(record.ghost_version).toBe('v2')
  expect(record.tools[0].output).toContain('has been updated')
  expect(record.ghost.usage.input_tokens).toBe(420)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /Trick!/ })).toBeDefined()
  await ui.press({ key: 'hide' })
  expect(await ui.find({ type: 'Text', text: /Trick!/ })).toBeUndefined()
  await ui.unmount()
})

test('a cursed command is sealed and logged', async ($, on) => {
  const files = new Map<string, string>()
  engine(on, files, [])

  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const ran = await $.tool.call({ tool: 'Bash', command: 'rm -rf node_modules' })

  expect(ran.deny).toContain('crypt is sealed')
  const record = JSON.parse((files.get(LOG) ?? '').trim())
  expect(record.kind).toBe('curse')
  expect(record.curse).toBe('rm -rf')
})

test('a safe command runs', async ($, on) => {
  engine(on, new Map(), [])

  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const ran = await $.tool.call({ tool: 'Bash', command: 'npm test' })

  expect(ran.deny).toBeUndefined()
})

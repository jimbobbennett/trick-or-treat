export type Verdict = 'treat' | 'trick'

export type LastVerdict = { verdict: Verdict; reason: string; turnId: string }

export type Tally = { treats: number; tricks: number; curses: number; skips: number }

declare module 'claude-code' {
  interface PluginState {
    'trick-or-treat': { last: LastVerdict | null; tally: Tally; isHidden: boolean }
  }
}

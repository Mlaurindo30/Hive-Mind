'use strict';
const readline = require('readline');
const { init } = require('./init');

function ask(rl, question, fallback) {
  return new Promise((resolve) => {
    rl.question(`${question}${fallback ? ` [${fallback}]` : ''}: `, (answer) => {
      resolve(answer.trim() || fallback || '');
    });
  });
}

async function wizard() {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  console.log('Hive-Mind — installation wizard\n');
  try {
    const profile = await ask(rl, 'Profile (local-min = lightweight; local-full = Milvus/RAGFlow via Docker)', 'local-min');
    const withTests = (await ask(rl, 'Run the test suite at the end? (y/N)', 'N')).toLowerCase().startsWith('y');
    const provider = await ask(rl, 'LLM provider for the Dream Cycle (google, openai, anthropic, ollama, skip)', 'skip');
    const env = {};
    if (provider !== 'skip') {
      env.HIVE_DREAMER_PROVIDER = provider;
      env.HIVE_DREAMER_MODEL = await ask(rl, `Model (${provider})`, provider === 'google' ? 'gemini-2.0-flash' : '');
      const keyVar = { google: 'GOOGLE_API_KEY', openai: 'OPENAI_API_KEY', anthropic: 'ANTHROPIC_API_KEY' }[provider];
      if (keyVar) {
        const key = await ask(rl, `${keyVar} (leave empty to configure later via setup-brain.sh)`);
        if (key) env[keyVar] = key;
      }
    }
    rl.close();
    return init({ profile, withTests, nonInteractive: true, env });
  } catch (e) {
    rl.close();
    throw e;
  }
}

module.exports = { wizard };

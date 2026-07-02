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
  console.log('Hive-Mind — assistente de instalação\n');
  try {
    const profile = await ask(rl, 'Perfil (local-min = leve; local-full = Milvus/RAGFlow via Docker)', 'local-min');
    const withTests = (await ask(rl, 'Rodar a suíte de testes ao final? (s/N)', 'N')).toLowerCase().startsWith('s');
    const provider = await ask(rl, 'Provider LLM do Dream Cycle (google, openai, anthropic, ollama, pular)', 'pular');
    const env = {};
    if (provider !== 'pular') {
      env.HIVE_DREAMER_PROVIDER = provider;
      env.HIVE_DREAMER_MODEL = await ask(rl, `Modelo (${provider})`, provider === 'google' ? 'gemini-2.0-flash' : '');
      const keyVar = { google: 'GOOGLE_API_KEY', openai: 'OPENAI_API_KEY', anthropic: 'ANTHROPIC_API_KEY' }[provider];
      if (keyVar) {
        const key = await ask(rl, `${keyVar} (deixe vazio para configurar depois via setup-brain.sh)`);
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

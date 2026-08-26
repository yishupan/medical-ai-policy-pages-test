import { mkdir, writeFile } from 'node:fs/promises';

await mkdir('data', { recursive: true });
await writeFile('data/run.json', JSON.stringify({
  generated_at: new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    dateStyle: 'medium',
    timeStyle: 'medium'
  }).format(new Date())
}, null, 2) + '\n');

# Graph editor

Web GUI for drawing small DARP instances, and a headless instance builder for producing them from a JSON spec. Both are documented in the repository [README](../../README.md#graph-editor).

```bash
npm install
npm run dev              # GUI
npm run build-instance -- examples/small-darp.json --out ../../my-instance   # headless
npm test                 # unit tests; DARP_E2E=1 npm test adds the browser end-to-end test
```

# Launchloom first proof

Use the bundled synthetic sample before configuring paid generation or live publishing.

```bash
launchloom doctor
launchloom first-proof --keep ./launchloom-proof
```

`first-proof` is the existing self-test pipeline exposed as the first product-evaluation action. It builds the bundled sample through the real local pipeline and writes evidence that can be inspected or attached to an issue. `--keep` preserves the generated films and launch kit in the directory you choose.

## What to inspect

1. The command exits successfully rather than only starting a server.
2. The kept output contains the generated sample films and launch kit.
3. The self-test report records the checks that actually ran.
4. A failure remains a failure with an actionable error instead of silently enabling a paid or live path.

## Truth boundary

- The bundled input is synthetic. Passing it proves the tested local pipeline completed for that sample; it is not proof of campaign performance or publishing reach.
- Paid video generation remains separately gated.
- Live social publishing remains separately gated and must not be enabled by `first-proof`.
- A generated launch kit is an artifact, not evidence that an external platform accepted or published it.

After the first proof, `launchloom serve` opens the local production board and `launchloom demo` exercises the running studio. Keep provider credentials and any live-publish configuration out of the first-proof path.

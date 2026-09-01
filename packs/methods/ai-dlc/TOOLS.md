# AI-DLC tool restrictions

- The Builder may use repository and CI tools the project permits.
- The Operator needs an explicit project environment grant before any deploy,
  release, or infrastructure apply. None of these is implied by the Builder role.
- Intent and unit-of-work changes require the Product Owner or the Architect.
- Exceptional workflow paths require an explicit transition and gate, not a flag.
- Merge, release publication, and deployment permissions are never implied by the
  Builder role.

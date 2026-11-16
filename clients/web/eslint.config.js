import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist/**', 'src/shared/api.generated.ts'] },
  ...tseslint.configs.recommended,
);

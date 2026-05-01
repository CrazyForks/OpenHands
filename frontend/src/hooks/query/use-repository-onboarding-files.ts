import { useQuery } from "@tanstack/react-query";
import GitService from "#/api/git-service/git-service.api";
import { RepositoryOnboardingFiles } from "#/types/git";
import { Provider } from "#/types/settings";

/**
 * Hook to check if a repository has onboarding files (AGENTS.md, REPO.md)
 * @param repository Repository name in format owner/repo
 * @param provider Git provider
 * @param branch Optional branch name
 * @param enabled Whether to enable the query
 * @returns Query result with onboarding file status
 */
export function useRepositoryOnboardingFiles(
  repository: string | null | undefined,
  provider: Provider | null | undefined,
  branch?: string | null,
  enabled: boolean = true,
) {
  return useQuery<RepositoryOnboardingFiles>({
    queryKey: [
      "repositories",
      "onboarding-files",
      repository,
      provider,
      branch,
    ],
    queryFn: async () => {
      if (!repository || !provider) {
        throw new Error("Repository and provider are required");
      }
      return GitService.getRepositoryOnboardingFiles(
        repository,
        provider,
        branch ?? undefined,
      );
    },
    enabled: !!repository && !!provider && enabled,
    staleTime: 1000 * 60 * 10, // 10 minutes - these files don't change often
    gcTime: 1000 * 60 * 30, // 30 minutes
  });
}

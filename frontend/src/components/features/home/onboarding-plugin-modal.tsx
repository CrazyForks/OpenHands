import { useTranslation } from "react-i18next";
import { OrgModal } from "#/components/shared/modals/org-modal";
import { I18nKey } from "#/i18n/declaration";

interface OnboardingPluginModalProps {
  onLoadPlugin: () => void;
  onDismiss: () => void;
  isLoading?: boolean;
}

export function OnboardingPluginModal({
  onLoadPlugin,
  onDismiss,
  isLoading = false,
}: OnboardingPluginModalProps) {
  const { t } = useTranslation();

  return (
    <OrgModal
      testId="onboarding-plugin-modal"
      title={t(I18nKey.HOME$LOAD_ONBOARDING_PLUGIN_TITLE)}
      description={t(I18nKey.HOME$LOAD_ONBOARDING_PLUGIN_DESCRIPTION)}
      primaryButtonText={t(I18nKey.BUTTON$LOAD_PLUGIN)}
      secondaryButtonText={t(I18nKey.BUTTON$NO_THANKS)}
      onPrimaryClick={onLoadPlugin}
      onClose={onDismiss}
      isLoading={isLoading}
      primaryButtonTestId="load-plugin-button"
      secondaryButtonTestId="no-thanks-button"
      fullWidthButtons
    />
  );
}

import React from "react";
import { useTranslation } from "react-i18next";
import { useSaveSettings } from "#/hooks/mutation/use-save-settings";
import { useSettings } from "#/hooks/query/use-settings";
import { useConfig } from "#/hooks/query/use-config";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SettingsSwitch } from "#/components/features/settings/settings-switch";
import { SettingsDropdownInput } from "#/components/features/settings/settings-dropdown-input";
import { AppSettingsInputsSkeleton } from "#/components/features/settings/app-settings/app-settings-inputs-skeleton";
import { I18nKey } from "#/i18n/declaration";
import {
  displayErrorToast,
  displaySuccessToast,
} from "#/utils/custom-toast-handlers";
import { retrieveAxiosErrorMessage } from "#/utils/retrieve-axios-error-message";
import { createPermissionGuard } from "#/utils/org/permission-guard";
import { Settings } from "#/types/settings";

export const clientLoader = createPermissionGuard(
  "manage_application_settings",
);

interface SandboxSettingsFormProps {
  settings: Settings;
  warmConfigs: Record<string, string>;
}

/**
 * Inner form. Mounted only once settings are loaded so the controlled toggle /
 * dropdown state can initialise from them without a sync effect.
 */
function SandboxSettingsForm({
  settings,
  warmConfigs,
}: SandboxSettingsFormProps) {
  const { t } = useTranslation();
  const { mutate: saveSettings, isPending } = useSaveSettings();

  const configKeys = Object.keys(warmConfigs);
  const items = configKeys.map((key) => ({ key, label: warmConfigs[key] }));

  // A saved selection that's no longer offered (operator changed the pools) is
  // treated as unset, so the dropdown won't show a stale value and Save requires
  // a fresh pick before re-enabling V2.
  const normaliseConfig = (value: string | null | undefined): string | null =>
    value && configKeys.includes(value) ? value : null;

  const initialUseV2 = !!settings.use_runtime_v2;
  const initialConfig = normaliseConfig(settings.warm_runtime_config);

  const [useV2, setUseV2] = React.useState(initialUseV2);
  const [selectedConfig, setSelectedConfig] = React.useState<string | null>(
    initialConfig,
  );

  const effectiveSelected = normaliseConfig(selectedConfig);

  // Persisted selection is independent of the toggle: turning V2 off leaves the
  // chosen pool in place (inert until re-enabled), so re-enabling restores it.
  const configToSave = effectiveSelected;

  // Must pick a pool before V2 can be enabled.
  const isValid = !useV2 || !!effectiveSelected;
  const isDirty = useV2 !== initialUseV2 || effectiveSelected !== initialConfig;
  const canSave = isValid && isDirty && !isPending;

  const formAction = () => {
    saveSettings(
      {
        use_runtime_v2: useV2,
        warm_runtime_config: configToSave,
      },
      {
        onSuccess: () => {
          displaySuccessToast(t(I18nKey.SETTINGS$SAVED));
        },
        onError: (error) => {
          const errorMessage = retrieveAxiosErrorMessage(error);
          displayErrorToast(errorMessage || t(I18nKey.ERROR$GENERIC));
        },
      },
    );
  };

  return (
    <form
      data-testid="sandbox-settings-screen"
      action={formAction}
      className="flex flex-col h-full justify-between"
    >
      <div className="flex flex-col gap-6">
        <p className="text-sm max-w-[680px]">
          {t(I18nKey.SETTINGS$SANDBOX_TAB_DESCRIPTION)}
        </p>

        <SettingsSwitch
          testId="use-runtime-v2-switch"
          name="use-runtime-v2-switch"
          isToggled={useV2}
          onToggle={setUseV2}
          isBeta
        >
          {t(I18nKey.SETTINGS$USE_RUNTIME_V2)}
        </SettingsSwitch>

        <SettingsDropdownInput
          testId="warm-runtime-config-input"
          name="warm-runtime-config-input"
          label={t(I18nKey.SETTINGS$WARM_RUNTIME_CONFIG)}
          items={items}
          selectedKey={effectiveSelected ?? undefined}
          isDisabled={!useV2}
          isClearable={false}
          onSelectionChange={(key) =>
            setSelectedConfig(key ? key.toString() : null)
          }
          wrapperClassName="w-full max-w-[680px]"
        />
      </div>

      <div className="flex gap-6 p-6 justify-end">
        <BrandButton
          testId="submit-button"
          variant="primary"
          type="submit"
          isDisabled={!canSave}
        >
          {!isPending && t("SETTINGS$SAVE_CHANGES")}
          {isPending && t("SETTINGS$SAVING")}
        </BrandButton>
      </div>
    </form>
  );
}

function SandboxSettingsScreen() {
  const { t } = useTranslation();
  const { data: settings, isLoading } = useSettings();
  const { data: config } = useConfig();

  const warmConfigs = config?.warm_runtime_configs ?? {};
  const isSaas = config?.app_mode === "saas";
  const hasConfigs = Object.keys(warmConfigs).length > 0;

  if (!settings || isLoading) {
    return <AppSettingsInputsSkeleton />;
  }

  // Defensive: the nav hides this tab unless SaaS + pools are configured, but a
  // direct navigation could still land here. Show a note rather than an empty
  // form.
  if (!isSaas || !hasConfigs) {
    return (
      <p data-testid="sandbox-settings-unavailable" className="text-sm">
        {t(I18nKey.SETTINGS$SANDBOX_NOT_AVAILABLE)}
      </p>
    );
  }

  return <SandboxSettingsForm settings={settings} warmConfigs={warmConfigs} />;
}

export default SandboxSettingsScreen;

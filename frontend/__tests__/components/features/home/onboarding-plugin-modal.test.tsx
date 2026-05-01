import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "test-utils";
import { OnboardingPluginModal } from "#/components/features/home/onboarding-plugin-modal";

describe("OnboardingPluginModal", () => {
  it("should render the modal with correct title and description", () => {
    // Arrange & Act
    renderWithProviders(
      <OnboardingPluginModal onLoadPlugin={vi.fn()} onDismiss={vi.fn()} />,
    );

    // Assert
    expect(
      screen.getByText("HOME$LOAD_ONBOARDING_PLUGIN_TITLE"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("HOME$LOAD_ONBOARDING_PLUGIN_DESCRIPTION"),
    ).toBeInTheDocument();
  });

  it("should call onLoadPlugin when the load plugin button is clicked", async () => {
    // Arrange
    const user = userEvent.setup();
    const onLoadPluginMock = vi.fn();
    renderWithProviders(
      <OnboardingPluginModal
        onLoadPlugin={onLoadPluginMock}
        onDismiss={vi.fn()}
      />,
    );

    // Act
    await user.click(screen.getByTestId("load-plugin-button"));

    // Assert
    expect(onLoadPluginMock).toHaveBeenCalledOnce();
  });

  it("should call onDismiss when the no thanks button is clicked", async () => {
    // Arrange
    const user = userEvent.setup();
    const onDismissMock = vi.fn();
    renderWithProviders(
      <OnboardingPluginModal onLoadPlugin={vi.fn()} onDismiss={onDismissMock} />,
    );

    // Act
    await user.click(screen.getByTestId("no-thanks-button"));

    // Assert
    expect(onDismissMock).toHaveBeenCalledOnce();
  });

  it("should disable buttons and show loading spinner when isLoading is true", () => {
    // Arrange & Act
    renderWithProviders(
      <OnboardingPluginModal
        onLoadPlugin={vi.fn()}
        onDismiss={vi.fn()}
        isLoading
      />,
    );

    // Assert
    expect(screen.getByTestId("load-plugin-button")).toBeDisabled();
    expect(screen.getByTestId("no-thanks-button")).toBeDisabled();
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("should have the correct test id for the modal", () => {
    // Arrange & Act
    renderWithProviders(
      <OnboardingPluginModal onLoadPlugin={vi.fn()} onDismiss={vi.fn()} />,
    );

    // Assert
    expect(screen.getByTestId("onboarding-plugin-modal")).toBeInTheDocument();
  });
});

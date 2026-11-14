defmodule FrontSeatWeb.SettingsLive.Ui do
  @moduledoc """
  Instance-wide UI settings, admin-only: display preferences shared by every
  project and every user, stored under `organization.settings["ui"]`.

  Writes go through `Accounts.update_ui_settings/2`, which merges into the
  `"ui"` key without disturbing `"setup_done"` or anything else in
  `organization.settings`.
  """

  use FrontSeatWeb, :live_view

  import FrontSeatWeb.SettingsLive.Components

  alias FrontSeat.Accounts

  @impl true
  def mount(_params, _session, socket) do
    organization = Accounts.get_organization!()

    {:ok,
     socket
     |> assign(page_title: "UI", organization: organization)
     |> assign_form(%{})}
  end

  @impl true
  def handle_event("validate", %{"ui" => params}, socket) do
    {:noreply, assign_form(socket, params)}
  end

  def handle_event("save", %{"ui" => params}, socket) do
    case Accounts.update_ui_settings(socket.assigns.current_scope, params) do
      {:ok, organization} ->
        {:noreply,
         socket
         |> assign(organization: organization)
         |> assign_form(%{})
         |> put_flash(:info, "UI settings saved.")}

      {:error, :unauthorized} ->
        {:noreply, put_flash(socket, :error, "Administrator access required.")}

      {:error, changeset} ->
        {:noreply, assign(socket, form: to_form(changeset, as: "ui"))}
    end
  end

  ## Template

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} nav={@nav} current_scope={@current_scope}>
      <.settings_page_header title="UI" back={~p"/settings"} />

      <div class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
        <div class="mx-auto flex w-full max-w-2xl flex-col gap-3.5">
          <.section_card label="Task cards">
            <.form for={@form} id="ui-form" phx-change="validate" phx-submit="save">
              <.input
                field={@form[:show_cost_on_cards]}
                type="checkbox"
                label="Show cost, token count, and duration on task cards"
              />

              <p class="mb-4 text-[12px] leading-relaxed text-text3">
                Applies to every board, for every user on this instance.
              </p>

              <div>
                <.button id="save-ui" variant="primary" type="submit">
                  Save
                </.button>
              </div>
            </.form>
          </.section_card>
        </div>
      </div>
    </Layouts.app>
    """
  end

  ## Internals

  defp assign_form(socket, params) do
    changeset =
      socket.assigns.organization
      |> Accounts.change_ui_settings(params)
      |> Map.put(:action, if(params == %{}, do: nil, else: :validate))

    assign(socket, form: to_form(changeset, as: "ui"))
  end
end

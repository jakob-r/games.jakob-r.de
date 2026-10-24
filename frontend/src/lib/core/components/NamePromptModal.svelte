<script lang="ts">
	import { PRESET_PLAYER_COLORS } from '$lib/core/color';
	import { profile } from '$lib/core/profile.svelte';
	import ScribblyBox from './ScribblyBox.svelte';
	import ScribblyButton from './ScribblyButton.svelte';

	let {
		onConfirm
	}: {
		onConfirm?: (name: string, color: string) => void;
	} = $props();

	let draftName = $state('');
	let initialized = $state(false);

	$effect(() => {
		if (profile.hydrated && !initialized) {
			draftName = '';
			initialized = true;
		}
	});

	function selectColor(hex: string) {
		profile.setColor(hex);
	}

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		const finalName = draftName.trim() || profile.name;
		profile.setName(finalName);
		onConfirm?.(profile.name, profile.primaryColor);
	}
</script>

{#if profile.hydrated && !profile.nameConfigured}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-[#1a1917]/40 p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="name-prompt-title"
	>
		<ScribblyBox seed={83} class="w-full max-w-sm bg-[#faf8f4] p-5 sm:p-6">
			<form onsubmit={handleSubmit} class="space-y-4">
				<div>
					<h2 id="name-prompt-title" class="font-hand text-2xl">What's your name?</h2>
					<p class="mt-1 text-xs text-[#6e6a63]">
						Choose a display name and ink color before playing.
					</p>
				</div>

				<div class="flex items-center gap-2.5">
					<span
						class="h-5 w-5 shrink-0 rounded-full border-[1.8px] border-[#1a1917]"
						style="background-color: {profile.primaryColor};"
					></span>
					<input
						type="text"
						bind:value={draftName}
						maxlength="28"
						placeholder={profile.name}
						aria-label="Your name"
						class="w-full rounded-md border-[1.8px] border-[#1a1917] bg-white px-3 py-2 text-base font-medium shadow-[2px_2px_0px_#1a1917] focus:outline-none"
					/>
				</div>

				<div class="flex flex-wrap items-center gap-2">
					{#each PRESET_PLAYER_COLORS as c}
						<button
							type="button"
							onclick={() => selectColor(c.hex)}
							title={c.name}
							aria-label={c.name}
							class="h-7 w-7 cursor-pointer rounded-full border-[1.8px] border-[#1a1917] transition-transform hover:scale-110 {profile.primaryColor.toLowerCase() ===
							c.hex.toLowerCase()
								? 'scale-110 ring-2 ring-[#1a1917] ring-offset-2 ring-offset-[#faf8f4]'
								: ''}"
							style="background-color: {c.hex};"
						></button>
					{/each}
				</div>

				<div class="flex justify-end pt-1">
					<ScribblyButton
						type="submit"
						variant="primary"
						accentColor={profile.primaryColor}
						class="w-full sm:w-auto"
					>
						Save & Join →
					</ScribblyButton>
				</div>
			</form>
		</ScribblyBox>
	</div>
{/if}

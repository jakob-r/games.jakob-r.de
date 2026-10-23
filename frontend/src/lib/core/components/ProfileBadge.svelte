<script lang="ts">
	import { PRESET_PLAYER_COLORS } from '$lib/core/color';
	import { profile } from '$lib/core/profile.svelte';

	let {
		onChange,
		compact = false
	}: {
		onChange?: (name: string, color: string) => void;
		compact?: boolean;
	} = $props();

	let open = $state(false);
	let draftName = $state(profile.name);

	$effect(() => {
		draftName = profile.name;
	});

	function handleNameInput(e: Event) {
		const target = e.currentTarget as HTMLInputElement;
		draftName = target.value;
		profile.setName(target.value);
		onChange?.(profile.name, profile.primaryColor);
	}

	function selectColor(hex: string) {
		profile.setColor(hex);
		onChange?.(profile.name, profile.primaryColor);
	}
</script>

{#if compact}
	<div class="relative">
		<button
			type="button"
			onclick={() => (open = !open)}
			class="inline-flex cursor-pointer items-center gap-2 rounded-md border-[1.6px] border-[#1a1917] bg-[#faf8f4] px-2.5 py-1 text-xs font-medium shadow-[1.5px_1.5px_0px_#1a1917] transition hover:bg-[#f2eee6]"
		>
			<span
				class="inline-block h-3 w-3 rounded-full border border-[#1a1917]"
				style="background-color: {profile.primaryColor};"
			></span>
			<span class="max-w-[110px] truncate">{profile.name}</span>
		</button>

		{#if open}
			<div
				class="absolute right-0 z-50 mt-2 w-64 rounded-md border-2 border-[#1a1917] bg-[#faf8f4] p-3 shadow-[4px_4px_0px_#1a1917]"
			>
				<div class="mb-2 flex items-center gap-2">
					<input
						type="text"
						value={draftName}
						oninput={handleNameInput}
						maxlength="28"
						placeholder="Your name"
						aria-label="Your name"
						class="w-full rounded border-[1.5px] border-[#1a1917] bg-white px-2.5 py-1.5 text-sm focus:outline-none"
					/>
					<button
						type="button"
						onclick={() => (open = false)}
						class="shrink-0 cursor-pointer text-xs text-[#6e6a63] hover:text-[#1a1917]"
					>
						Done
					</button>
				</div>
				<div class="flex flex-wrap gap-1.5">
					{#each PRESET_PLAYER_COLORS as c}
						<button
							type="button"
							onclick={() => selectColor(c.hex)}
							title={c.name}
							aria-label={c.name}
							class="h-6 w-6 cursor-pointer rounded-full border-[1.5px] border-[#1a1917] transition-transform hover:scale-110 {profile.primaryColor.toLowerCase() ===
							c.hex.toLowerCase()
								? 'ring-2 ring-[#1a1917] ring-offset-2 ring-offset-[#faf8f4]'
								: ''}"
							style="background-color: {c.hex};"
						></button>
					{/each}
					<label
						title="Custom color"
						class="inline-flex h-6 w-6 cursor-pointer items-center justify-center rounded-full border-[1.5px] border-dashed border-[#1a1917] text-[10px] font-bold"
					>
						+
						<input
							type="color"
							value={profile.primaryColor}
							oninput={(e) => selectColor((e.currentTarget as HTMLInputElement).value)}
							class="sr-only"
						/>
					</label>
				</div>
			</div>
		{/if}
	</div>
{:else}
	<div class="space-y-3">
		<div class="flex items-center gap-2.5">
			<span
				class="h-5 w-5 shrink-0 rounded-full border-[1.8px] border-[#1a1917]"
				style="background-color: {profile.primaryColor};"
			></span>
			<input
				id="player-name-input"
				type="text"
				value={draftName}
				oninput={handleNameInput}
				maxlength="28"
				placeholder="Your name..."
				aria-label="Your name"
				class="w-full rounded-md border-[1.8px] border-[#1a1917] bg-white px-3 py-2 text-base font-medium shadow-[2px_2px_0px_#1a1917] focus:outline-none"
			/>
		</div>

		<div class="flex flex-wrap items-center gap-2.5">
			{#each PRESET_PLAYER_COLORS as c}
				<button
					type="button"
					onclick={() => selectColor(c.hex)}
					title={c.name}
					aria-label={c.name}
					class="h-8 w-8 cursor-pointer rounded-full border-[1.8px] border-[#1a1917] transition-transform hover:scale-110 {profile.primaryColor.toLowerCase() ===
					c.hex.toLowerCase()
						? 'scale-110 ring-2 ring-[#1a1917] ring-offset-2 ring-offset-[#faf8f4]'
						: ''}"
					style="background-color: {c.hex};"
				></button>
			{/each}

			<label
				title="Pick custom ink color"
				class="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border-[1.6px] border-dashed border-[#1a1917] px-2.5 text-xs font-medium hover:bg-[#f2eee6]"
			>
				<span>Custom</span>
				<input
					type="color"
					value={profile.primaryColor}
					oninput={(e) => selectColor((e.currentTarget as HTMLInputElement).value)}
					class="h-4 w-4 cursor-pointer border-0 bg-transparent p-0"
				/>
			</label>
		</div>
	</div>
{/if}

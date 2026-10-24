export interface PlayerInfo {
	player_id: string;
	name: string;
	color: string;
	is_ready: boolean;
	is_connected: boolean;
	score: number;
	multiplier: number;
	multiplier_remaining_ms: number;
	last_correct_at: string | null;
	cursor?: { row: number | null; col: number | null } | null;
}

export interface RoomStateSnapshot<TState = Record<string, unknown>> {
	type: 'room_state';
	room_id: string;
	game_slug: string;
	status: 'lobby' | 'playing' | 'finished';
	host_player_id: string;
	config: Record<string, unknown>;
	state: TState;
	players: PlayerInfo[];
	server_time: string;
}

export type ServerEvent =
	| RoomStateSnapshot
	| {
			type: 'mistake_flash';
			row: number;
			col: number;
			value: number;
			player_id: string;
			points_delta: number;
	  }
	| {
			type: 'cell_scored';
			row: number;
			col: number;
			value: number;
			player_id: string;
			points_delta: number;
			base_points: number;
			multiplier: number;
			reason: string;
	  }
	| {
			type: 'line_drawn';
			orientation: 'h' | 'v';
			row: number;
			col: number;
			player_id: string;
			closed_squares: { row: number; col: number }[];
			points_delta: number;
			next_player_id: string | null;
	  }
	| {
			type: 'cell_revealed';
			row: number;
			col: number;
			player_id: string;
			revealed_count: number;
			cells: { row: number; col: number; adjacent: number }[];
			points_delta: number;
	  }
	| {
			type: 'mine_hit';
			row: number;
			col: number;
			player_id: string;
			points_delta: number;
	  }
	| {
			type: 'flag_placed';
			row: number;
			col: number;
			player_id: string;
			points_delta: number;
	  }
	| {
			type: 'flag_removed';
			row: number;
			col: number;
			player_id: string;
			points_delta: number;
	  }
	| {
			type: 'flag_challenged';
			row: number;
			col: number;
			player_id: string;
			owner_id: string;
			was_correct: boolean;
			challenger_delta: number;
			owner_delta: number;
			revealed_count?: number;
			cells?: { row: number; col: number; adjacent: number }[];
	  }
	| {
			type: 'word_played';
			word: string;
			player_id: string;
			positions: { row: number; col: number }[];
			word_points: number;
			points_delta: number;
			next_player_id: string | null;
	  }
	| {
			type: 'word_rejected';
			player_id: string;
			word: string;
			reason: string;
	  }
	| {
			type: 'turn_passed';
			player_id: string;
			next_player_id: string | null;
			consecutive_passes: number;
	  }
	| {
			type: 'cursor_update';
			player_id: string;
			row: number | null;
			col: number | null;
	  }
	| {
			type: 'room_deleted';
			room_id: string;
	  }
	| {
			type: 'error';
			message: string;
	  };

export class RoomSocketClient {
	connected = $state(false);
	reconnecting = $state(false);
	error = $state<string | null>(null);
	room = $state<RoomStateSnapshot | null>(null);

	private ws: WebSocket | null = null;
	private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	private manualClose = false;
	private eventHandlers: ((ev: ServerEvent) => void)[] = [];

	private gameSlug = '';
	private roomId = '';
	private playerId = '';
	private playerName = '';
	private playerColor = '';

	connect(params: {
		gameSlug: string;
		roomId: string;
		playerId: string;
		name: string;
		color: string;
	}): void {
		this.gameSlug = params.gameSlug;
		this.roomId = params.roomId;
		this.playerId = params.playerId;
		this.playerName = params.name;
		this.playerColor = params.color;
		this.manualClose = false;
		this.openSocket();
	}

	private openSocket(): void {
		if (typeof window === 'undefined') return;
		if (this.ws) {
			try {
				this.ws.close();
			} catch {
				// ignore
			}
		}

		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		const query = new URLSearchParams({
			player_id: this.playerId,
			name: this.playerName,
			color: this.playerColor
		});
		const url = `${protocol}//${window.location.host}/ws/${this.gameSlug}/${this.roomId}?${query.toString()}`;

		const socket = new WebSocket(url);
		this.ws = socket;

		socket.onopen = () => {
			this.connected = true;
			this.reconnecting = false;
			this.error = null;
		};

		socket.onmessage = (event) => {
			try {
				const data = JSON.parse(event.data) as ServerEvent;
				if (data.type === 'room_state') {
					this.room = data;
				} else if (data.type === 'cursor_update' && this.room) {
					this.room = {
						...this.room,
						players: this.room.players.map((p) =>
							p.player_id === data.player_id
								? { ...p, cursor: { row: data.row, col: data.col } }
								: p
						)
					};
				} else if (data.type === 'room_deleted') {
					this.manualClose = true;
					this.error = 'This game session was permanently deleted.';
				} else if (data.type === 'error') {
					this.error = data.message;
				}
				for (const cb of this.eventHandlers) {
					cb(data);
				}
			} catch (err) {
				console.error('Failed to parse WS message', err);
			}
		};

		socket.onclose = (ev) => {
			this.connected = false;
			if (this.manualClose || ev.code === 4004 || ev.code === 4000) {
				if (ev.code === 4004) {
					this.error = 'Room not found.';
				}
				return;
			}
			this.reconnecting = true;
			this.reconnectTimer = setTimeout(() => {
				this.openSocket();
			}, 1200);
		};
	}

	onEvent(handler: (ev: ServerEvent) => void): () => void {
		this.eventHandlers.push(handler);
		return () => {
			this.eventHandlers = this.eventHandlers.filter((h) => h !== handler);
		};
	}

	send(payload: Record<string, unknown>): void {
		if (this.ws && this.ws.readyState === WebSocket.OPEN) {
			this.ws.send(JSON.stringify(payload));
		}
	}

	syncProfile(playerId: string, name: string, color: string): void {
		this.playerId = playerId;
		this.playerName = name;
		this.playerColor = color;
		this.send({
			type: 'player_sync',
			player_id: playerId,
			name,
			color
		});
	}

	setReady(isReady: boolean): void {
		this.send({ type: 'set_ready', is_ready: isReady });
	}

	updateConfig(config: Record<string, unknown>): void {
		this.send({ type: 'update_config', config });
	}

	startGame(): void {
		this.send({ type: 'start_game' });
	}

	returnToLobby(): void {
		this.send({ type: 'return_to_lobby' });
	}

	sendAction(action: Record<string, unknown>): void {
		this.send({ type: 'game_action', action });
	}

	sendCursor(row: number | null, col: number | null): void {
		this.send({ type: 'cursor_move', row, col });
	}

	disconnect(): void {
		this.manualClose = true;
		if (this.reconnectTimer) {
			clearTimeout(this.reconnectTimer);
			this.reconnectTimer = null;
		}
		if (this.ws) {
			this.ws.close();
			this.ws = null;
		}
		this.connected = false;
	}
}

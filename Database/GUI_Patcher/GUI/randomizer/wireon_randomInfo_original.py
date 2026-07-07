class RandomizationInfo:
    def __init__(self):
        self.current_progress=0
        self.max_progress=1
        self.filters={"special":["no_arena_monsters"]}
        self.seed=0
        self.generate_spoiler=True
        self.mods=["always_flee"]
        self.level_up_mode={}
        self.skill_points_mode={}
        self.item_mode={}
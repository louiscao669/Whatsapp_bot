"""Errors raised by participant-dashboard services."""


class StorePurchaseError(Exception):
    pass


class ProfilePhotoUploadError(Exception):
    pass


class ProfilePhotoNotFoundError(Exception):
    pass


class CosmeticUpdateError(Exception):
    pass


class StreakPauseUpdateError(Exception):
    pass


class ChestRewardError(Exception):
    pass


class DashboardAnswerError(Exception):
    pass


class CommunityTeamError(Exception):
    pass


class DashboardSettingsError(Exception):
    pass

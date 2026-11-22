"""Hashtags: sempre as do nicho, nada de palavra solta da transcrição ("#sabe") nem palavrão."""
from stark_engine.copywriter import heuristic_copy, niche_hashtags


def test_niche_hashtags():
    assert niche_hashtags("Grand Theft Auto VI") == ["#gta6", "#gtavi", "#gta"]
    assert niche_hashtags("GTA 6")[:2] == ["#gta6", "#gtavi"]
    assert niche_hashtags("Minecraft") == ["#minecraft"] and niche_hashtags("") == []


def test_hashtags_skip_filler_noise_and_profanity():
    text = ("sabe o que eu fiz? a polícia chegou com cinco helicópteros, porra, a polícia cercou o prédio "
            "e os helicópteros voando")
    c = heuristic_copy("Polícia com helicópteros", text, ["pataquedas", "sabe", "purei"], niche_hashtags("GTA VI"))
    tiktok = c["hashtags"]["tiktok"]
    assert tiktok[:2] == ["#gta6", "#gtavi"] and "#policia" in tiktok and tiktok[-1] == "#fyp"
    every = {t for tags in c["hashtags"].values() for t in tags}
    assert not every & {"#sabe", "#pataquedas", "#purei", "#porra"}
    assert c["captions"]["instagram"].endswith("#reels")

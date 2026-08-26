def signature_distance(
    signature_a,
    signature_b
):

    if (
        not signature_a
        or not signature_b
    ):
        return 999

    def normalize_image_vector(
        image
    ):

        image = np.asarray(
            image,
            dtype=np.float32
        ).flatten()

        if image.size == 0:
            return None

        # Alte Signaturen können z.B.
        # 16x16 = 256 Werte haben.
        # Neue Signaturen haben
        # 24x24 = 576 Werte.
        #
        # Für den Vergleich werden ALLE
        # Signaturen auf 24x24 gebracht.

        side = int(
            round(
                np.sqrt(
                    image.size
                )
            )
        )

        if (
            side <= 0
            or side * side
            != image.size
        ):
            return None

        try:

            image_2d = image.reshape(
                side,
                side
            )

            image_2d = cv2.resize(
                image_2d,
                (24, 24),
                interpolation=cv2.INTER_AREA
            )

            return image_2d.flatten()

        except Exception:

            return None

    results = []

    for hist_a, image_a in signature_a:

        hist_a = np.asarray(
            hist_a,
            dtype=np.float32
        ).flatten()

        normalized_a = (
            normalize_image_vector(
                image_a
            )
        )

        if (
            hist_a.size == 0
            or normalized_a is None
        ):
            continue

        best = 999

        for hist_b, image_b in signature_b:

            hist_b = np.asarray(
                hist_b,
                dtype=np.float32
            ).flatten()

            normalized_b = (
                normalize_image_vector(
                    image_b
                )
            )

            if (
                hist_b.size == 0
                or normalized_b is None
            ):
                continue

            # ---------------------------------
            # HISTOGRAMM
            # ---------------------------------

            # Falls irgendwann auch die
            # Histogrammgröße geändert wird,
            # darf der Bot ebenfalls nicht
            # abstürzen.

            if hist_a.size == hist_b.size:

                try:

                    hist_distance = (
                        cv2.compareHist(
                            hist_a,
                            hist_b,
                            cv2.HISTCMP_BHATTACHARYYA
                        )
                    )

                except Exception:

                    hist_distance = 1.0

            else:

                hist_distance = 1.0

            # ---------------------------------
            # BILDVERGLEICH
            # ---------------------------------

            image_distance = float(
                np.mean(
                    np.abs(
                        normalized_a
                        - normalized_b
                    )
                )
            )

            # ---------------------------------
            # GESAMTABSTAND
            # ---------------------------------

            distance = (
                hist_distance * 0.55
                + image_distance * 0.45
            )

            best = min(
                best,
                distance
            )

        if best < 999:

            results.append(
                best
            )

    if not results:

        return 999

    return float(
        np.mean(
            results
        )
    )
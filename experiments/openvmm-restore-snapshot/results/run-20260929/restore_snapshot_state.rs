    async fn restore_snapshot_state(
        &mut self,
        saved_state: SavedState,
        restore_time: Option<(Duration, u64, Option<u64>)>,
    ) -> anyhow::Result<()> {
        if let Some((_, saved_frequency, saved_apic_frequency)) = restore_time {
            let destination_frequency = self
                .inner
                .partition
                .tsc_frequency_hz()?
                .context("destination backend does not expose a guest TSC frequency")?;
            anyhow::ensure!(
                destination_frequency == saved_frequency,
                "destination TSC frequency {destination_frequency} Hz does not match saved frequency {saved_frequency} Hz"
            );
            self.inner.partition.set_tsc_frequency_hz(saved_frequency)?;
            let destination_apic_frequency = self
                .inner
                .partition
                .apic_frequency_hz()?
                .context("destination backend does not expose a local APIC frequency")?;
            if let Some(saved_apic_frequency) = saved_apic_frequency {
                anyhow::ensure!(
                    destination_apic_frequency == saved_apic_frequency,
                    "destination APIC frequency {destination_apic_frequency} Hz does not match saved frequency {saved_apic_frequency} Hz"
                );
            }
        }

        let saved_state_restore = openvmm_defs::profile::ProfileSpan::start();
        self.restore(saved_state)
            .await
            .context("loadedvm restore failed")?;
        saved_state_restore.complete("restore", "saved_state_restore", Default::default());

        if let Some((downtime, frequency, saved_apic_frequency)) = restore_time {
            let state_time_advance = openvmm_defs::profile::ProfileSpan::start();
            self.state_units
                .advance_time(downtime)
                .await
                .context("failed to advance restored VM time")?;
            state_time_advance.complete("restore", "state_time_advance", Default::default());

            #[cfg(guest_arch = "x86_64")]
            {
                let apic_frequency =
                    match saved_apic_frequency {
                        Some(frequency) => frequency,
                        None => self.inner.partition.apic_frequency_hz()?.context(
                            "destination backend does not expose a local APIC frequency",
                        )?,
                    };
                let vp_tsc_advance = openvmm_defs::profile::ProfileSpan::start();
                self.inner
                    .partition_unit
                    .advance_tsc(downtime, frequency, Some(apic_frequency))
                    .await
                    .context("failed to advance restored vCPU TSC")?;
                vp_tsc_advance.complete("restore", "vp_tsc_advance", Default::default());
            }

            let backend_time_advance = openvmm_defs::profile::ProfileSpan::start();
            self.inner
                .partition
                .advance_snapshot_time(downtime)
                .context("failed to advance backend snapshot clock")?;
            backend_time_advance.complete("restore", "backend_time_advance", Default::default());
        }

        let restore_vp_stop = openvmm_defs::profile::ProfileSpan::start();
        self.restore_start_guard = Some(self.inner.partition_unit.temporarily_stop_vps().await);
        restore_vp_stop.complete("restore", "restore_vp_stop", Default::default());

        Ok(())
    }

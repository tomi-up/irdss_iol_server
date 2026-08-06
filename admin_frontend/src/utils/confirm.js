import Swal from 'sweetalert2'

// Shared confirmation dialog so every destructive/impactful admin action (rotate,
// revoke, deactivate) looks the same, and matches the SweetAlert2 style already
// used across the mock_hospitals HIS frontend.
export async function confirmAction({ title, text, confirmText = 'Confirm', danger = true }) {
  const result = await Swal.fire({
    title,
    text,
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: confirmText,
    cancelButtonText: 'Cancel',
    confirmButtonColor: danger ? '#dc2626' : '#4f46e5',
    cancelButtonColor: '#64748b',
    reverseButtons: true,
    focusCancel: true,
  })
  return result.isConfirmed
}
